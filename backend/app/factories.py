"""组件工厂：按配置装配 LLM 版 / 启发式版组件。

策略选择规则（零配置可用，配置即升级）：
- LLM_API_KEY 存在   → LLMScorer / LLMProber / LLMPlanner / LLM 简历解析
- LLM_API_KEY 缺失   → 启发式全家桶（确定性，离线可跑，测试基线）
- JUDGE0_URL 存在    → Judge0Sandbox（编码题客观判题）；否则 None（纯主观评审）
- VOICE_ENABLED 打开 → 语音通道启用（VAD/ASR/TTS 按 VOICE_*_PROVIDER 选择）；
  默认关闭，且默认 provider 全为 dummy —— 协议与流程可验证，但不具备真实识别能力。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agent.planner import HeuristicPlanner, LLMPlanner, Planner
from app.agent.prober import LLMProber, SkillTreeProber
from app.agent.scorer import HeuristicScorer, LLMScorer, Scorer
from app.agent.skill_tree import SkillTree, load_skill_tree
from app.config import Settings
from app.llm.client import LLMClient, OpenAICompatibleLLM
from app.rag.question_bank import QuestionBank
from app.sandbox.judge0 import Judge0Sandbox
from app.voice.asr import ASRClient, DummyASR, XfyunASR
from app.voice.channel import VoiceChannel
from app.voice.tts import DummyTTS, EdgeTTSClient, TTSClient
from app.voice.vad import VAD, EnergyVAD, SileroVAD


@lru_cache(maxsize=8)
def _load_assets_cached(
    skill_tree_dir: str, question_bank_dir: str, retrieval_provider: str,
    index_path: str, index_stamp: str, dimensions: int, rrf_k: int, candidate_k: int,
    provider="hash", model="char-ngram-hash-v1", revision="1", base_url="", api_key=None, timeout=15,
) -> tuple[dict[str, SkillTree], QuestionBank]:
    trees = load_skill_tree(Path(skill_tree_dir))
    bank = QuestionBank.load(Path(question_bank_dir))
    if retrieval_provider != "bm25":
        from app.rag.embeddings import build_embedder
        from app.rag.hybrid_retriever import HybridRetriever
        from app.rag.retriever import BM25Retriever
        from app.rag.vector_index import VectorIndex, IndexError
        embedder = build_embedder(Settings(_env_file=None,embedding_provider=provider,
            embedding_model=model,embedding_dimensions=dimensions,embedding_revision=revision,
            embedding_base_url=base_url,embedding_api_key=api_key,embedding_timeout_seconds=timeout))
        reason = None
        try:
            index = VectorIndex.load(Path(index_path), bank.questions, embedder.spec)
        except IndexError as exc:
            index, reason = None, str(exc)
        retriever = HybridRetriever(BM25Retriever(bank.questions), embedder, index,
            mode=retrieval_provider, rrf_k=rrf_k, candidate_k=candidate_k,
            unavailable_reason=reason, unavailable_version=index_stamp)
        bank = QuestionBank(bank.questions, retriever)
    return trees, bank


def load_assets(settings: Settings) -> tuple[dict[str, SkillTree], QuestionBank]:
    """加载技能树与题库（进程内缓存）。

    注意：Settings 是 pydantic 模型（不可哈希），因此缓存键用路径字符串。
    """
    stamp = "not_required"
    if settings.retrieval_provider != "bm25":
        try:
            info = settings.retrieval_index_path.stat()
            stamp = f"{info.st_mtime_ns}:{info.st_size}"
        except OSError:
            stamp = "missing"
    return _load_assets_cached(str(settings.skill_tree_dir), str(settings.question_bank_dir),
        settings.retrieval_provider, str(settings.retrieval_index_path), stamp,
        settings.embedding_dimensions, settings.retrieval_rrf_k, settings.retrieval_candidate_k,
        settings.embedding_provider,settings.embedding_model,settings.embedding_revision,
        settings.embedding_base_url,settings.embedding_api_key,settings.embedding_timeout_seconds)


def build_llm(settings: Settings) -> LLMClient | None:
    if not settings.llm_api_key:
        return None
    from app.llm.limiter import configure_limit
    configure_limit(settings.llm_max_concurrency)
    return OpenAICompatibleLLM(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        max_concurrency=settings.llm_max_concurrency,
        backoff_base_seconds=settings.llm_backoff_base_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
        thinking_mode=settings.llm_thinking_mode,
    )


def build_interview_budget(settings: Settings):
    """每场面试的用量预算（P2 步骤 2.1）。未配置时返回不限额度的对象。"""
    from app.llm.budget import TokenBudget

    return TokenBudget(
        limit_tokens=settings.llm_budget_tokens_per_interview,
        limit_cost=settings.llm_budget_cost_per_interview,
        price_input_per_million=settings.llm_price_input_per_million,
        price_output_per_million=settings.llm_price_output_per_million,
    )


def _scoring_config_version(settings: Settings) -> str:
    """评分相关配置的摘要：进入缓存键，配置变化必须让缓存失效。"""
    import hashlib

    material = "|".join(str(part) for part in (
        settings.pass_score, settings.probe_score, settings.probe_depth_limit,
        settings.weak_score, settings.llm_temperature,
        settings.llm_max_output_tokens, settings.llm_thinking_mode,
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def build_scorer(settings: Settings, llm: LLMClient | None) -> Scorer:
    if llm is None:
        return HeuristicScorer(config_version=_scoring_config_version(settings))
    from app.agent.score_cache import get_score_cache

    return LLMScorer(
        llm,
        cache=get_score_cache(),
        model_id=settings.llm_model,
        config_version=_scoring_config_version(settings),
    )


def build_prober(settings: Settings, llm: LLMClient | None, tree: SkillTree) -> SkillTreeProber:
    return LLMProber(llm, tree) if llm else SkillTreeProber(tree)


def build_planner(settings: Settings, llm: LLMClient | None, tree: SkillTree) -> Planner:
    return LLMPlanner(llm, tree) if llm else HeuristicPlanner(tree)


def build_sandbox(settings: Settings) -> Judge0Sandbox | None:
    if not settings.judge0_url:
        return None
    from app.sandbox.admission import admission
    admission.configure(settings.sandbox_max_concurrency, settings.sandbox_max_waiters)
    return Judge0Sandbox(
        settings.judge0_url,
        api_key=settings.judge0_api_key,
        language_id=settings.judge0_language_id,
        timeout=settings.sandbox_timeout_seconds,
        queue_timeout=settings.sandbox_queue_timeout_seconds,
        max_response_bytes=settings.sandbox_max_response_bytes,
        max_testcases=settings.sandbox_max_testcases,
    )


# ---------------------------------------------------------------- 语音（P1）

# 注意：VAD / ASR / TTS 都是**有状态**的（VAD 累计计数、ASR 会话、TTS 连接），
# 因此这些 builder 每次调用都返回新实例，绝不做缓存——
# 跨连接复用会让两个用户的语音流互相污染。


def build_vad(settings: Settings) -> VAD:
    if settings.voice_vad_provider == "silero":
        return SileroVAD()
    return EnergyVAD(
        rms_threshold=settings.voice_rms_threshold,
        silence_ms=settings.voice_silence_ms,
        min_speech_ms=settings.voice_min_speech_ms,
        max_utterance_ms=settings.voice_max_utterance_seconds * 1000.0,
    )


def build_asr(settings: Settings) -> ASRClient:
    if settings.voice_asr_provider == "doubao":
        from app.voice.doubao import DoubaoASR, DoubaoVoiceOptions
        return DoubaoASR(DoubaoVoiceOptions.from_settings(settings))
    if settings.voice_asr_provider == "xfyun":
        return XfyunASR(app_id="", api_key="", secret_key="")
    return DummyASR(default_text=settings.voice_asr_dummy_text)


def build_tts(settings: Settings) -> TTSClient:
    if settings.voice_tts_provider == "doubao":
        from app.voice.doubao import DoubaoTTS, DoubaoVoiceOptions
        return DoubaoTTS(DoubaoVoiceOptions.from_settings(settings))
    if settings.voice_tts_provider == "edge":
        return EdgeTTSClient()
    return DummyTTS()


def build_voice_channel(settings: Settings) -> VoiceChannel:
    return VoiceChannel(
        vad=build_vad(settings),
        asr=build_asr(settings),
        sample_rate=settings.voice_sample_rate,
        preroll_ms=settings.voice_preroll_ms,
        max_frame_bytes=settings.voice_max_frame_bytes,
        max_utterance_seconds=settings.voice_max_utterance_seconds,
    )
