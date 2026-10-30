"""领域模型层。

Agent、RAG、API 各层只依赖本模块定义的纯数据结构，
不依赖 ORM / FastAPI / LLM SDK —— 保证核心逻辑可单测、可移植。
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------- 题库域


@dataclass(frozen=True)
class AnswerPoint:
    """评分锚点：一个要点 + 命中关键词。命中判定由 Scorer 实现。"""

    point: str
    keywords: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "AnswerPoint":
        return cls(point=str(d["point"]), keywords=tuple(d.get("keywords") or []))


@dataclass(frozen=True)
class TestCase:
    input: str
    expected: str

    @classmethod
    def from_dict(cls, d: dict) -> "TestCase":
        return cls(input=str(d["input"]), expected=str(d["expected"]))


@dataclass(frozen=True)
class Question:
    id: str
    position: str
    theme: str
    difficulty: str  # easy / mid / hard
    content: str
    answer_points: tuple[AnswerPoint, ...] = ()
    is_coding: bool = False
    testcases: tuple[TestCase, ...] = ()
    source: str = "builtin"

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(
            id=str(d["id"]),
            position=str(d["position"]),
            theme=str(d["theme"]),
            difficulty=str(d.get("difficulty", "mid")),
            content=str(d["content"]),
            answer_points=tuple(AnswerPoint.from_dict(p) for p in d.get("answer_points", [])),
            is_coding=bool(d.get("is_coding", False)),
            testcases=tuple(TestCase.from_dict(t) for t in d.get("testcases", [])),
            source=str(d.get("source", "builtin")),
        )


# ---------------------------------------------------------------- 评分域


@dataclass(frozen=True)
class EvidenceRef:
    """一条评分证据：引用原文片段 + 字符位置 + 所支撑的锚点。

    ⚠️ 它证明的是"这句话确实出现在回答里、且落在某个锚点上"，
    **不证明推理正确**（见 docs/技术实现步骤.md 步骤 2.2）。
    """

    anchor: str
    quote: str
    start: int
    end: int


@dataclass(frozen=True)
class ScoreOrigin:
    source: str = "unknown"
    scorer_version: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    prompt_digest: str | None = None
    config_version: str | None = None
    cached: bool = False
    fallback_reason: str | None = None
    sandbox_applied: bool = False


@dataclass(frozen=True)
class ScoreResult:
    """结构化评分：分数必须有 evidence 支撑（反幻觉设计）。"""

    score: float  # 0-10
    dimensions: dict[str, float] = field(default_factory=dict)
    key_points_hit: tuple[str, ...] = ()
    key_points_missed: tuple[str, ...] = ()
    evidence: str = ""
    sandbox: dict | None = None  # 代码题客观判题结果（可选）
    #: 结构化证据（不落库：持久化层是显式字段映射，未列出即不写入）。
    #: 需要进报告时再补一列并配迁移。
    evidence_refs: tuple[EvidenceRef, ...] = ()
    origin: ScoreOrigin = field(default_factory=ScoreOrigin)

    @property
    def passed(self) -> bool:
        return self.score >= 7.0


@dataclass
class ScoreRecord:
    """一次回答的完整记录（会话内累积，最终落库）。"""

    question_id: str
    theme: str
    content: str
    result: ScoreResult
    probe_depth: int = 0
    answer_text: str = ""
    turn_id: str = ""
    main_question_id: str = ""
    skill_node_id: str | None = None
    question_version: str | None = None
    main_question_version: str | None = None
    question_difficulty: str | None = None
    is_coding: bool | None = None


# ---------------------------------------------------------------- 规划域


@dataclass(frozen=True)
class PlanItem:
    theme: str
    weight: float
    difficulty: str
    question_count: int
    include_coding: bool = False


@dataclass
class ResumeData:
    """简历结构化结果。skills 用于规划器加权，projects 供追问引擎引用。"""

    skills: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    education: str = ""


# ---------------------------------------------------------------- 沙箱域


@dataclass(frozen=True)
class SandboxResult:
    passed: int
    total: int
    detail: list[dict] = field(default_factory=list)

    @property
    def pass_ratio(self) -> float:
        return self.passed / self.total if self.total else 0.0


# ---------------------------------------------------------------- 事件域
# WS 下行事件统一为 dict（JSON 直传）。这里只约束事件类型常量，保持协议单点维护。


class EventType:
    STATE = "state"                    # 状态机变更
    GREETING = "greeting"              # 开场白
    QUESTION = "question"              # 抛出问题（含追问/编码题）
    ANSWER_ACK = "answer_ack"          # 已收到回答
    SCORE = "score"                    # 评分事件
    AGENT_MESSAGE = "agent_message"    # 面试官口语化反应
    CLOSING = "closing"                # 收尾语
    REPORT_READY = "report_ready"      # 报告就绪
    ERROR = "error"

    # ---- 语音链路（P1，见 docs/技术实现步骤.md 步骤 1.1）----
    # 上行音频不产生业务事件；以下均为下行或内部记录用常量。
    ASR_PARTIAL = "asr_partial"            # 转写中间结果（覆盖语义，前端灰字）
    ASR_FINAL = "asr_final"                # 本段发言最终文本
    TTS_CHUNK = "tts_chunk"                # TTS 音频分片（PCM，帧头带采样率）
    TTS_END = "tts_end"                    # 一个 utterance 播报结束
    BARGE_IN_ACK = "barge_in_ack"          # 打断已生效
    VOICE_GAP = "voice_gap"                # 序号缺口：该段缓冲已重置
    VOICE_EMPTY = "voice_empty"            # 未识别到有效语音
    VOICE_ERROR = "voice_error"            # 识别/合成失败，提示可回退打字
    VOICE_CANCELLED = "voice_cancelled"    # 发言被取消


class VoiceRecordType:
    """只落库、不下发的事件类型（供回放与评测统计）。"""

    UTTERANCE_CANCELLED = "utterance_cancelled"
    UTTERANCE_DROPPED = "utterance_dropped"
    TTS_FAILED = "tts_failed"
    TURN_DISCARDED = "turn_discarded"


Event = dict  # alias：所有事件 {"type": EventType.X, ...}
