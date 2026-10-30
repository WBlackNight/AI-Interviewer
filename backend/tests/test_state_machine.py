"""状态机单元测试：转移表正确性与非法转移防护。"""
from __future__ import annotations

import pytest

from app.agent.state_machine import (
    ALLOWED_TRANSITIONS,
    InterviewState,
    IllegalTransitionError,
    can_transition,
    transition,
)


def test_happy_path_full_flow():
    """完整面试的合法主路径。"""
    path = [
        InterviewState.GREETING,
        InterviewState.QUESTIONING,
        InterviewState.PROBING,
        InterviewState.QUESTIONING,
        InterviewState.CODING,
        InterviewState.CLOSING,
        InterviewState.REPORT,
        InterviewState.FINISHED,
    ]
    state = path[0]
    for nxt in path[1:]:
        state = transition(state, nxt)
    assert state is InterviewState.FINISHED


def test_probing_can_self_loop():
    assert can_transition(InterviewState.PROBING, InterviewState.PROBING)


def test_greeting_cannot_jump_to_coding():
    with pytest.raises(IllegalTransitionError):
        transition(InterviewState.GREETING, InterviewState.CODING)


def test_finished_is_terminal():
    assert ALLOWED_TRANSITIONS[InterviewState.FINISHED] == frozenset()
    with pytest.raises(IllegalTransitionError):
        transition(InterviewState.FINISHED, InterviewState.GREETING)


def test_every_state_has_entry_in_table():
    assert set(ALLOWED_TRANSITIONS) == set(InterviewState)
