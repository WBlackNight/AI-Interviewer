"""显式面试状态机。

面试流程不采用 ReAct 自由循环，而是受控状态机：
- 转移表集中定义，非法转移直接抛异常（fail-fast，便于测试与审计）；
- 每次转移对应一个 interview_event 落库，全程可回放、可复现。
"""
from __future__ import annotations

from enum import Enum


class InterviewState(str, Enum):
    GREETING = "greeting"        # 开场：确认岗位、说明流程
    QUESTIONING = "questioning"  # 主题提问
    PROBING = "probing"          # 动态追问（受深度上限约束）
    CODING = "coding"            # 手撕代码环节
    CLOSING = "closing"          # 收尾：反问环节
    REPORT = "report"            # 报告生成
    FINISHED = "finished"        # 终态


#: 合法转移表。键 = 当前状态，值 = 允许进入的目标状态集合。
ALLOWED_TRANSITIONS: dict[InterviewState, frozenset[InterviewState]] = {
    InterviewState.GREETING: frozenset({InterviewState.QUESTIONING}),
    InterviewState.QUESTIONING: frozenset(
        {
            InterviewState.PROBING,
            InterviewState.QUESTIONING,  # 同题重问 / 换下一题（自转移）
            InterviewState.CODING,
            InterviewState.CLOSING,
        }
    ),
    InterviewState.PROBING: frozenset(
        {
            InterviewState.PROBING,      # 继续下钻（深度受限）
            InterviewState.QUESTIONING,  # 追问通过 → 回到提问主流程
            InterviewState.CODING,
            InterviewState.CLOSING,
        }
    ),
    InterviewState.CODING: frozenset(
        {InterviewState.CODING, InterviewState.QUESTIONING, InterviewState.CLOSING}
    ),
    InterviewState.CLOSING: frozenset({InterviewState.REPORT}),
    InterviewState.REPORT: frozenset({InterviewState.FINISHED}),
    InterviewState.FINISHED: frozenset(),
}


class IllegalTransitionError(ValueError):
    """非法状态转移 —— 属于程序缺陷，必须在开发期暴露而非吞掉。"""


def can_transition(src: InterviewState, dst: InterviewState) -> bool:
    return dst in ALLOWED_TRANSITIONS[src]


def transition(src: InterviewState, dst: InterviewState) -> InterviewState:
    if not can_transition(src, dst):
        raise IllegalTransitionError(
            f"非法状态转移: {src.value} -> {dst.value}；"
            f"合法目标: {[s.value for s in ALLOWED_TRANSITIONS[src]] or ['<终态，无出边>']}"
        )
    return dst
