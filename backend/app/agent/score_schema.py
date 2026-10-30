"""评分载荷的严格 schema 与证据校验（P2 步骤 2.2）。

评审要求逐条落地：

| 要求 | 落点 |
|---|---|
| 总分与每个维度为**有限的 0–10**，禁止 NaN / 负数 | ``ScorePayload`` 字段校验器 |
| 禁止**假锚点**：锚点必须属于当前题 | ``build_score_result`` 的集合校验 |
| evidence 用**回答原文片段及位置** | ``EvidenceRef``（含 ``start`` / ``end``） |
| evidence 必须**映射到具体评分锚点** | 每条引用都要能落到锚点，否则拒绝 |
| 拒绝异常字段 | ``extra="forbid"`` + ``strict=True`` |

⚠️ **边界（必须如实声明）**：本模块能证明"引用是真实存在的原文"，也能证明
"引用落在某个锚点上"，**但不能证明推理正确**——模型完全可能引用真实片段却得出错误结论。
因此它只用于**拒绝明显伪造与结构异常**，评分质量仍需人工标注评测（见 P4 的 κ 目标）。
"""
from __future__ import annotations

import hashlib
import math
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.integrity import apply_injection_policy
from app.domain import EvidenceRef, Question, ScoreResult

#: 提示词版本：进入缓存键。修改 SYSTEM_PROMPT 时必须同步递增，
#: 否则旧缓存会被错误复用。
PROMPT_VERSION = "score-prompt-v7"

DIMENSION_KEYS = ("技术深度", "表达逻辑", "岗位匹配")

MAX_QUOTES = 5
MAX_QUOTE_CHARS = 300
MAX_EVIDENCE_CHARS = 500
#: 无锚点命中时的分数上限（与启发式口径一致）。
NO_HIT_SCORE_CAP = 3.0


class ScorePayload(BaseModel):
    """模型必须返回的结构。严格模式：类型不符直接拒绝，不做宽容转换。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    score: float
    dimensions: dict[str, float]
    key_points_hit: list[str]
    key_points_missed: list[str]
    evidence: str = Field(min_length=1, max_length=MAX_EVIDENCE_CHARS)
    evidence_quotes: list[str] = Field(min_length=1, max_length=MAX_QUOTES)

    @field_validator("score", "dimensions", mode="before")
    @classmethod
    def _reject_non_numeric_containers(cls, value):
        # pydantic 的 strict 模式已挡住大多数情况；这里额外挡住 bool
        # （Python 中 bool 是 int 的子类，会让 True 冒充 1.0）。
        if isinstance(value, bool):
            raise ValueError("评分数值不能是布尔值")
        return value

    @field_validator("score")
    @classmethod
    def _score_range(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 10.0:
            raise ValueError("总分必须是 0–10 的有限数值")
        return round(value, 1)

    @field_validator("dimensions")
    @classmethod
    def _dimensions_exact_keys(cls, value: dict[str, float]) -> dict[str, float]:
        keys = set(value)
        if keys != set(DIMENSION_KEYS):
            raise ValueError(f"维度必须是 {list(DIMENSION_KEYS)}，实际为 {sorted(keys)}")
        for key, item in value.items():
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError(f"维度 {key} 不是数值")
            if not math.isfinite(item) or not 0.0 <= item <= 10.0:
                raise ValueError(f"维度 {key} 必须是 0–10 的有限数值")
        return {key: round(float(item), 1) for key, item in value.items()}

    @field_validator("key_points_hit", "key_points_missed")
    @classmethod
    def _points_non_empty_strings(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("要点列表必须是非空字符串")
        if len(set(value)) != len(value):
            raise ValueError("要点列表存在重复项")
        return value

    @field_validator("evidence_quotes")
    @classmethod
    def _quotes_shape(cls, value: list[str]) -> list[str]:
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("引用必须是非空字符串")
            if len(item) > MAX_QUOTE_CHARS:
                raise ValueError(f"单条引用不得超过 {MAX_QUOTE_CHARS} 字")
        return value


def anchors_digest(question: Question) -> str:
    """锚点版本摘要：锚点变化时缓存必须失效。"""
    material = "|".join(
        f"{p.point}:{','.join(p.keywords)}" for p in question.answer_points
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def evidence_candidates(question: Question, answer: str) -> list[dict]:
    """提供有界的连续原文候选，帮助模型引用；候选不代表语义命中。"""
    quotes: dict[str, list[str]] = {}
    for point in question.answer_points:
        for term, flags in [(point.point, 0), *((term, re.IGNORECASE) for term in point.keywords)]:
            if not term or len(term) > MAX_QUOTE_CHARS:
                continue
            match = re.search(re.escape(term), answer, flags)
            if match is None:
                continue
            context_chars = min(40, MAX_QUOTE_CHARS - len(match.group()))
            start = max(0, match.start() - context_chars)
            quote = answer[start:start + MAX_QUOTE_CHARS]
            supported = _anchors_supported_by(quote, question.answer_points)
            if point.point in supported:
                quotes[quote] = list(supported)
                break
    return [{"quote": quote, "literal_anchors": anchors} for quote, anchors in quotes.items()]


def build_score_result(payload: ScorePayload, question: Question, answer: str) -> ScoreResult:
    """把已通过 schema 的载荷校验为可用的 ``ScoreResult``。

    这里只做**跨字段**校验（schema 管不到的）：锚点归属、引用真实性、
    引用→锚点映射、无命中封顶、注入处置。
    """
    if not answer.strip():
        raise ValueError("空回答不接受 LLM 评分")

    anchor_points = {p.point for p in question.answer_points}
    hit, missed = set(payload.key_points_hit), set(payload.key_points_missed)
    if hit & missed:
        raise ValueError("同一要点不能既命中又缺失")
    if hit | missed != anchor_points:
        # 假锚点的入口：模型编造了本题不存在的要点。
        unknown = (hit | missed) - anchor_points
        raise ValueError(f"评分锚点不属于当前题：{sorted(unknown) or '存在遗漏要点'}")

    refs = _build_evidence_refs(
        payload.evidence_quotes, answer, question,
        anchors_hit=hit, require_mapping=bool(hit),
    )
    if hit and not refs:
        raise ValueError("命中了要点但没有任何引用支撑")

    score, dimensions, note = apply_injection_policy(
        score=payload.score, dimensions=payload.dimensions,
        hits=tuple(payload.key_points_hit), answer=answer,
    )
    if not hit:
        # 与启发式同一口径：没有锚点支撑就不允许高分。
        score = min(score, NO_HIT_SCORE_CAP)
        dimensions = {k: min(v, NO_HIT_SCORE_CAP) for k, v in dimensions.items()}

    evidence = payload.evidence.strip()
    if refs:
        rendered = "；".join(
            f"{ref.anchor}「{ref.quote}」@{ref.start}-{ref.end}" for ref in refs
        )
        evidence = f"{evidence}；引用：{rendered}"
    if note:
        evidence = f"{evidence}；{note}"

    return ScoreResult(
        score=round(score, 1),
        dimensions=dimensions,
        key_points_hit=tuple(payload.key_points_hit),
        key_points_missed=tuple(payload.key_points_missed),
        evidence=evidence[:MAX_EVIDENCE_CHARS + 300],
        evidence_refs=refs,
    )


def _build_evidence_refs(
    quotes: list[str],
    answer: str,
    question: Question,
    *,
    anchors_hit: set[str],
    require_mapping: bool,
) -> tuple[EvidenceRef, ...]:
    """把每条引用定位到原文，并映射到它支撑的锚点。

    引用必须**逐字出现在回答中**（拒绝伪造，位置由查找得到）。

    ``require_mapping`` 只在**存在命中锚点**时为真。原因是一个逻辑必然性：
    若一个锚点都没命中，引用就不可能映射到任何锚点——此时仍硬性要求映射，
    等于让模型永远无法合法地给出低分（第一版实现就是这样自相矛盾的）。
    无命中场景下，引用只用于说明"候选人到底说了什么"。
    """
    refs: list[EvidenceRef] = []
    for quote in quotes:
        start = answer.find(quote)
        if start < 0:
            raise ValueError("评分引用不属于原回答（疑似伪造引用）")
        anchors = _anchors_supported_by(quote, question.answer_points)
        if not anchors:
            if require_mapping:
                raise ValueError("引用未映射到任何评分锚点")
            continue
        for anchor in anchors:
            refs.append(
                EvidenceRef(anchor=anchor, quote=quote, start=start, end=start + len(quote))
            )
    # 每个命中都需要自己的证据；仅交集非空会放过其余无依据的命中。
    if not anchors_hit <= {ref.anchor for ref in refs}:
        raise ValueError("命中的要点没有任何引用支撑")
    return tuple(refs)


def _anchors_supported_by(quote: str, points) -> tuple[str, ...]:
    """引用里出现了该锚点的要点原文或其关键词 → 视为支撑该锚点。"""
    lowered = quote.lower()
    supported: list[str] = []
    for point in points:
        if point.point in quote:
            supported.append(point.point)
            continue
        if point.keywords and any(keyword.lower() in lowered for keyword in point.keywords):
            supported.append(point.point)
    return tuple(supported)
