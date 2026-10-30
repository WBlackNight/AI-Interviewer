"""应用配置：全部经 pydantic-settings 从环境变量 / .env 读取。

设计原则：
- 默认值保证「零配置可跑」（SQLite + 启发式组件，无任何外部依赖）；
- 提供密钥后启用 LLM / Judge0；离线向量检索由RETRIEVAL_PROVIDER显式选择。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator, field_validator
from typing import Literal

# 项目根目录 = backend/ 的上一级
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_name: str = "Mock Interviewer"
    debug: bool = True

    # ---- 存储 ----
    # 开发默认 SQLite；生产/演示切 postgresql+psycopg://... 或经 Docker Compose
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"  # 预留：会话缓存 / 已问题集合

    # ---- LLM（OpenAI 兼容协议：DeepSeek / GLM / Qwen 均可）----
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = Field(default=0.3, ge=0, le=2, allow_inf_nan=False)
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=120, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    # 仅支持thinking参数的供应商显式配置；None不发送扩展字段。
    llm_thinking_mode: Literal["enabled", "disabled"] | None = None
    # P2 步骤 2.1：有限重试（仅可重试类别）、并发上限、严格模式
    llm_max_attempts: int = Field(default=3, ge=1, le=6)
    llm_max_concurrency: int = Field(default=4, ge=1, le=32)
    llm_backoff_base_seconds: float = Field(default=0.5, gt=0, le=10)
    #: 严格模式：模型失败直接抛错而不回退。仅用于开发/联调，生产必须关闭。
    llm_strict_mode: bool = False
    #: 每场面试用量预算：0 表示不限制 token。
    llm_budget_tokens_per_interview: int = Field(default=0, ge=0)
    #: 每场金额预算与单价表：**默认全部为空**——未配置时不计算金额，
    #: 只统计 token。本项目不内置任何模型价格，避免伪造出看似精确的成本。
    llm_budget_cost_per_interview: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    llm_price_input_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    llm_price_output_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    # ---- 评分缓存（P2 步骤 2.2）----
    #: **默认关闭**：让"无缓存重复评测"成为基线口径。开启后命中缓存的两次评测
    #: 连模型都没调用，不能当作可重复性证据。
    scoring_cache_enabled: bool = False
    scoring_cache_max_entries: int = Field(default=512, ge=0, le=100000)
    scoring_cache_ttl_seconds: float = Field(default=3600.0, gt=0, le=86400)

    # ---- 检索：离线词法基线/智谱Embedding-3；API Key不作为检索模式开关 ----
    retrieval_provider: Literal["bm25", "vector", "hybrid"] = "bm25"
    retrieval_index_path: Path = PROJECT_ROOT / "data" / "retrieval" / "question_index.json"
    retrieval_candidate_k: int = Field(default=20, ge=1, le=1000)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    embedding_provider: Literal["hash", "zhipu"] = "hash"
    embedding_dimensions: int = Field(default=256, ge=16, le=4096)
    # 远程配置仅zhipu消费；hash仍可无密钥离线运行。
    embedding_api_key: str | None = Field(default=None, repr=False)
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_model: str = "char-ngram-hash-v1"
    embedding_revision: str = "1"
    embedding_timeout_seconds: float = Field(default=15, gt=0, le=60, allow_inf_nan=False)

    # ---- 代码沙箱（可选：配置后编码题启用客观判题）----
    judge0_url: str | None = None
    judge0_api_key: str | None = None
    judge0_language_id: int = 71  # Python 3
    sandbox_max_concurrency: int = Field(default=2, ge=1, le=32)
    sandbox_max_waiters: int = Field(default=8, ge=0, le=128)
    sandbox_queue_timeout_seconds: float = Field(default=2, gt=0, le=30, allow_inf_nan=False)
    sandbox_timeout_seconds: float = Field(default=15, gt=0, le=60, allow_inf_nan=False)
    sandbox_max_response_bytes: int = Field(default=262144, ge=1024, le=1048576)
    sandbox_max_testcases: int = Field(default=12, ge=1, le=100)

    # ---- 数据目录 ----
    question_bank_dir: Path = PROJECT_ROOT / "data" / "question_bank"
    skill_tree_dir: Path = PROJECT_ROOT / "data" / "skill_tree"

    # ---- PDF 简历：先有界接收，再在可终止的独立进程提取 ----
    resume_pdf_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    resume_pdf_max_pages: int = Field(default=10, ge=1, le=50)
    resume_pdf_max_text_chars: int = Field(default=20000, ge=100, le=20000)
    resume_pdf_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    resume_upload_timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)

    # ---- 面试策略（对应技术方案文档 4.2 节）----
    pass_score: float = Field(default=7.0, ge=0, le=10, allow_inf_nan=False)
    # 所有低于通过线的回答仍追问；probe_score 区分基础澄清与深入追问。
    probe_score: float = Field(default=4.0, ge=0, le=10, allow_inf_nan=False)
    probe_depth_limit: int = Field(default=3, ge=0, le=10)
    max_plan_themes: int = Field(default=3, ge=1, le=8)
    weak_score: float = Field(default=7.0, ge=0, le=10, allow_inf_nan=False)
    ws_max_message_bytes: int = Field(default=100000, ge=1024, le=1000000)
    ws_idle_timeout_seconds: float = Field(default=300, gt=0)
    turn_timeout_seconds: float = Field(default=180, gt=0)

    # ---- 语音链路（P1；默认关闭，保证零配置仍是可用的文字模式）----
    voice_enabled: bool = False
    voice_vad_provider: Literal["energy", "silero"] = "energy"
    voice_asr_provider: Literal["dummy", "xfyun", "doubao"] = "dummy"
    voice_tts_provider: Literal["dummy", "edge", "doubao"] = "dummy"
    # 豆包Seeduplex JSON协议；密钥只留在服务端，不复用文本模型凭据。
    doubao_voice_api_key: str | None = Field(default=None, repr=False)
    doubao_voice_auth_mode: Literal["api_key", "legacy"] = "api_key"
    doubao_voice_app_id: str | None = Field(default=None, pattern=r"^[0-9]{1,32}$", repr=False)
    doubao_voice_access_token: str | None = Field(default=None, repr=False)
    doubao_voice_model: Literal["1.2.6.1"] = "1.2.6.1"
    doubao_voice_speaker: str = Field(default="zh_female_xiaohe_jupiter_bigtts", pattern=r"^[A-Za-z0-9_-]{1,100}$")
    doubao_voice_timeout_seconds: float = Field(default=15, gt=0, le=60, allow_inf_nan=False)
    doubao_voice_session_seconds: float = Field(default=120, gt=0, le=180, allow_inf_nan=False)
    doubao_voice_max_connections: int = Field(default=2, ge=1, le=16)
    voice_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    voice_max_frame_bytes: int = Field(default=6400, ge=640, le=64000)
    # 静默/最短语音阈值：**实验起点**，需用录音标注验证端点误差后定稿
    # （docs/技术实现步骤.md 步骤 1.3）。
    voice_silence_ms: float = Field(default=700.0, gt=0, le=5000)
    voice_min_speech_ms: float = Field(default=200.0, ge=0, le=2000)
    voice_rms_threshold: float = Field(default=500.0, ge=0)
    voice_preroll_ms: float = Field(default=400.0, gt=0, le=2000)
    voice_max_utterance_seconds: float = Field(default=120.0, gt=0, le=600)
    voice_audio_queue_max: int = Field(default=256, ge=8, le=4096)
    # 音频帧的独立频率预算：10 帧/秒是常态，不能用文字消息的 60 条/分钟限流。
    voice_max_frames_per_minute: int = Field(default=900, ge=60, le=6000)
    # 文字模式是否也合成语音：默认关闭（打字却听到语音会显得怪异），
    # 冒烟脚本与"只看不测"的演示可显式打开以验证播放通路。
    voice_tts_text_mode: bool = False
    # DummyASR 的固定返回文本：仅供协议测试与延迟探针使用，
    # **不具备识别能力**，不得用于任何质量结论。
    voice_asr_dummy_text: str = ""
    # Local test mail never leaves the loopback SMTP sink; production uses TLS SMTP.
    mail_mode: Literal['disabled', 'local_test', 'smtp'] = 'disabled'
    smtp_host: str = '127.0.0.1'
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_security: Literal['starttls', 'ssl', 'none'] = 'starttls'
    smtp_username: str | None = Field(default=None, repr=False)
    smtp_password: str | None = Field(default=None, repr=False)
    mail_from: str = 'qingzhan@example.test'
    auth_challenge_secret: str | None = Field(default=None,min_length=32,repr=False)

    @field_validator("retrieval_index_path")
    @classmethod
    def resolve_retrieval_path(cls, value: Path) -> Path:
        # CLI从项目根启动，API从backend启动：同一配置必须指向同一文件。
        return value if value.is_absolute() else PROJECT_ROOT / value

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.llm_budget_cost_per_interview is not None and (
            self.llm_price_input_per_million is None or self.llm_price_output_per_million is None):
            raise ValueError("金额预算须同时配置输入和输出单价")
        if self.probe_score > self.pass_score:
            raise ValueError("PROBE_SCORE 不得超过 PASS_SCORE")
        if self.voice_min_speech_ms >= self.voice_max_utterance_seconds * 1000:
            raise ValueError("VOICE_MIN_SPEECH_MS 不能超过单次发言上限")
        if self.voice_enabled and "doubao" in (self.voice_asr_provider, self.voice_tts_provider):
            if self.doubao_voice_auth_mode == "legacy":
                if not self.doubao_voice_app_id or not (self.doubao_voice_access_token or '').strip():
                    raise ValueError("旧版豆包语音须配置DOUBAO_VOICE_APP_ID和DOUBAO_VOICE_ACCESS_TOKEN")
            elif not self.doubao_voice_api_key or not self.doubao_voice_api_key.strip():
                raise ValueError("启用豆包语音须配置DOUBAO_VOICE_API_KEY")
            if self.voice_sample_rate != 16000:
                raise ValueError("豆包语音输入须为16000Hz")
        expected = self.voice_sample_rate * 2 // 10  # 100ms 帧的字节数
        if self.voice_max_frame_bytes < expected:
            raise ValueError("VOICE_MAX_FRAME_BYTES 不得小于一个 100ms 帧")
        return self

    # ---- API ----
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
