"""作答与简历的完整性检测（P2 步骤 2.2）。

评审要求："空回答、否定句、关键词堆砌、提示注入和'我不会'不能仅因长度或关键词得到高分。
简历和回答属于待评估数据，不得作为指令覆盖评分规则。"

关键词堆砌与"我不会"在启发式评分里已有处理（见 ``scorer.HeuristicScorer``：
覆盖率之外的剩余文本不足10字且缺少两段独立关系说明时判为堆砌；否定句保守处理）。
本模块补齐**提示注入**的检测与处置口径。

处置口径（刻意区分两种情况，避免误伤诚实的候选人）：
- 检测到注入**且没有任何锚点命中** → 硬性压到 3 分以内（纯粹想操纵评分）；
- 检测到注入**但有锚点命中** → 不扣分，仅在证据里标注，保持透明与可审计。

误报的代价是不对称的：误压分伤害诚实候选人，漏压分只是让一段无效文本拿到低分。
因此这里只在"没有实质内容"时才施压。
"""
from __future__ import annotations

import re

#: 常见提示注入/越权指令模式。只做**检测与记录**，不做内容过滤删除——
#: 删除会破坏"证据必须是原话"的可追溯性。
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_instructions", re.compile(
        r"忽略(以上|上述|前面|之前)?(所有)?(指令|提示|要求|规则)|"
        r"ignore\s+(all\s+)?(previous\s+)?instructions?", re.IGNORECASE)),
    ("role_override", re.compile(
        r"你现在是|扮演|假设你是|从现在起你是|"
        r"you\s+are\s+now|act\s+as\b", re.IGNORECASE)),
    ("score_demand", re.compile(
        r"(给我|直接给|必须给|一律给|全部给)\s*(满分|10分|十分|高分)|"
        r"满分通过|评\s*10\s*分|score\s*(me\s*)?10", re.IGNORECASE)),
    ("system_prompt_probe", re.compile(
        r"(输出|打印|泄露|显示|告诉我)(你的)?(系统)?(提示词|prompt|system)",
        re.IGNORECASE)),
    ("rule_disable", re.compile(
        r"(取消|跳过|无视|关闭)(评分|打分|审查|校验|规则)|"
        r"(don'?t|do\s+not)\s+(score|evaluate|check)", re.IGNORECASE)),
)

#: 无实质内容时的分数上限（仅在检测到注入时生效）。
INJECTION_SCORE_CAP = 3.0


def detect_prompt_injection(text: str) -> tuple[str, ...]:
    """返回命中的模式标签（去重、保持定义顺序）。未命中返回空元组。"""
    if not text:
        return ()
    return tuple(label for label, pattern in _INJECTION_PATTERNS if pattern.search(text))


def has_substantive_content(text: str, *, min_chars: int = 10) -> bool:
    """粗判是否含有实质内容。

    去掉标点与空白后长度不足 ``min_chars`` 视为无实质内容
    （与启发式评分的堆砌判定同一口径，避免两处阈值不一致）。
    """
    return len(re.sub(r"[\W\d_]+", "", text or "")) >= min_chars


def apply_injection_policy(
    *, score: float, dimensions: dict[str, float], hits: tuple[str, ...] | list[str],
    answer: str, cap: float = INJECTION_SCORE_CAP,
) -> tuple[float, dict[str, float], str | None]:
    """按处置口径返回修正后的 (score, dimensions, 标注)。

    返回的标注为 ``None`` 表示未检测到注入。
    """
    labels = detect_prompt_injection(answer)
    if not labels:
        return score, dimensions, None
    label_text = "、".join(labels)
    if hits:
        # 有实质命中：保持透明，不扣分。
        return score, dimensions, f"检测到疑似越权指令（{label_text}），但回答命中评分锚点，未调整分数"
    return (
        min(score, cap),
        {key: min(value, cap) for key, value in dimensions.items()},
        f"检测到疑似越权指令（{label_text}）且未命中任何评分锚点，分数上限 {cap}",
    )
