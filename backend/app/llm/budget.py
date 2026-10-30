"""每场面试的用量与成本预算（P2 步骤 2.1）。

评审要求："设置超时、有限重试、并发上限和**每场成本预算**"。

为什么用 ContextVar 而不是构造参数：模型客户端是**每轮新建**的
（`ws.load_session` 里 `build_llm(settings)`），而预算是**每场面试**的粒度。
`asyncio.to_thread` 会复制当前上下文，因此在进入工作线程前设置预算，
线程内的客户端即可读到——无需把预算层层透传进 Scorer/Prober/Planner。

成本口径（重要）：
- **token 数来自供应商响应的 usage，是事实**；
- **金额只有在运维显式配置了单价表时才计算**，否则只报 token。
  本项目不内置任何价格表——凭空填价格会伪造出看似精确的成本数字。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

from app.llm.errors import BudgetExceeded


@dataclass
class TokenBudget:
    """一场面试的用量上限。``limit_tokens <= 0`` 表示不限制。"""

    limit_tokens: int = 0
    limit_cost: float | None = None
    price_input_per_million: float | None = None
    price_output_per_million: float | None = None
    used_tokens: int = 0
    used_cost: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def enabled(self) -> bool:
        return self.limit_tokens > 0 or self.limit_cost is not None

    @property
    def cost_configured(self) -> bool:
        return (
            self.price_input_per_million is not None
            and self.price_output_per_million is not None
        )

    def charge(self, *, tokens_in: int, tokens_out: int) -> None:
        """记账；超限抛 ``BudgetExceeded``。

        先记账再判定：把已发生（已计费）的用量真实记下来，
        否则错误报告里的用量会少算最后一次调用。
        """
        tokens = max(tokens_in, 0) + max(tokens_out, 0)
        cost = 0.0
        if self.cost_configured:
            cost = (
                max(tokens_in, 0) / 1_000_000 * float(self.price_input_per_million)
                + max(tokens_out, 0) / 1_000_000 * float(self.price_output_per_million)
            )
        with self._lock:
            self.used_tokens += tokens
            self.used_cost += cost
            over_tokens = self.limit_tokens > 0 and self.used_tokens > self.limit_tokens
            over_cost = self.limit_cost is not None and self.used_cost > self.limit_cost
            state = (self.used_tokens, round(self.used_cost, 6), self.limit_tokens, self.limit_cost)
        if over_tokens or over_cost:
            raise BudgetExceeded(
                f"面试用量预算已耗尽（tokens={state[0]}/{state[2]} cost={state[1]}/{state[3]}）"
            )

    def check(self) -> None:
        with self._lock:
            if ((self.limit_tokens > 0 and self.used_tokens >= self.limit_tokens)
                    or (self.limit_cost is not None and self.used_cost >= self.limit_cost)):
                raise BudgetExceeded("模型预算已耗尽，后续调用已阻止")

    def snapshot(self) -> dict:
        with self._lock:
            data = {
                "used_tokens": self.used_tokens,
                "limit_tokens": self.limit_tokens,
            }
            if self.cost_configured:
                data["used_cost"] = round(self.used_cost, 6)
                data["limit_cost"] = self.limit_cost
                data["cost_note"] = "单价由运维在配置中提供"
            else:
                # 不编造金额：未配置单价时明确说明。
                data["used_cost"] = None
                data["cost_note"] = "未配置单价表，只统计 token，不计算金额"
            return data


_current: ContextVar[TokenBudget | None] = ContextVar("llm_budget", default=None)
_budgets: dict[str, TokenBudget] = {}
_registry_lock = threading.Lock()


def budget_for(interview_id: str, factory) -> TokenBudget:
    """按面试 id 取（或新建）预算对象，保证跨轮次累计。"""
    with _registry_lock:
        budget = _budgets.get(interview_id)
        if budget is None:
            budget = factory()
            _budgets[interview_id] = budget
        return budget


def release_budget(interview_id: str) -> None:
    """面试结束时移除，避免长期驻留。"""
    with _registry_lock:
        _budgets.pop(interview_id, None)


@contextmanager
def use_budget(budget: TokenBudget | None) -> Iterator[None]:
    token = _current.set(budget)
    try:
        yield
    finally:
        _current.reset(token)


def current_budget() -> TokenBudget | None:
    return _current.get()
