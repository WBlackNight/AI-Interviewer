"""LLM 调用遥测（P2 步骤 2.1）。

目的：让"回退"**可观察**。评审要求核心是这一条——
**网络失败不得把启发式结果标成"LLM 验证成功"**。
仅靠 health 里的 `llm_enabled` 只能说明"配置存在"，说明不了任何调用成功过。

实现取向：
- 进程内累加计数（线程安全）＋结构化日志，作为开发/演示期的可观察面；
- **不是**指标后端，不持久化、不跨进程聚合。生产应接真正的 metrics 系统，
  本模块的定位在文档中明确写出，避免被误当成可观测性方案的全部。

分类口径（三者互斥，不可混用）：
- ``llm_success``：模型调用成功且输出通过校验；
- ``heuristic_fallback``：模型失败，结果由启发式产生；
- ``error_raised``：严格模式下失败直接抛出（用于开发期暴露缺陷）。
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from app.llm.errors import LLMErrorKind, VALIDATION_REASONS

logger = logging.getLogger(__name__)


class CallOutcome(str, Enum):
    LLM_SUCCESS = "llm_success"
    HEURISTIC_FALLBACK = "heuristic_fallback"
    ERROR_RAISED = "error_raised"


@dataclass
class ComponentStats:
    calls: int = 0
    llm_success: int = 0
    heuristic_fallback: int = 0
    error_raised: int = 0
    latency_ms_total: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error_kinds: Counter = field(default_factory=Counter)
    validation_reasons: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "llm_success": self.llm_success,
            "heuristic_fallback": self.heuristic_fallback,
            "error_raised": self.error_raised,
            "fallback_rate": round(self.heuristic_fallback / self.calls, 4) if self.calls else 0.0,
            "avg_latency_ms": round(self.latency_ms_total / self.calls, 1) if self.calls else 0.0,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "error_kinds": dict(self.error_kinds),
            "validation_reasons": dict(self.validation_reasons),
        }


class LLMTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._components: dict[str, ComponentStats] = {}

    def _stats(self, component: str) -> ComponentStats:
        return self._components.setdefault(component, ComponentStats())

    def record(
        self,
        component: str,
        outcome: CallOutcome,
        *,
        latency_ms: float = 0.0,
        error_kind: LLMErrorKind | None = None,
        detail: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        safe_reason = detail if detail in VALIDATION_REASONS else "-"
        with self._lock:
            stats = self._stats(component)
            stats.calls += 1
            stats.latency_ms_total += max(latency_ms, 0.0)
            stats.tokens_in += max(tokens_in, 0)
            stats.tokens_out += max(tokens_out, 0)
            if outcome is CallOutcome.LLM_SUCCESS:
                stats.llm_success += 1
            elif outcome is CallOutcome.HEURISTIC_FALLBACK:
                stats.heuristic_fallback += 1
            else:
                stats.error_raised += 1
            if error_kind is not None:
                stats.error_kinds[error_kind.value] += 1
            if error_kind is LLMErrorKind.BAD_PAYLOAD and safe_reason != "-":
                stats.validation_reasons[safe_reason] += 1

        if outcome is not CallOutcome.LLM_SUCCESS:
            # 结构化日志：只记录类别与组件，不含回答/简历/凭据。
            logger.warning(
                "llm_outcome component=%s outcome=%s error_kind=%s latency_ms=%.1f detail=%s",
                component, outcome.value,
                error_kind.value if error_kind else "-",
                latency_ms, safe_reason,
            )

    def snapshot(self) -> dict:
        with self._lock:
            return {name: stats.as_dict() for name, stats in sorted(self._components.items())}

    def reset(self) -> None:
        with self._lock:
            self._components.clear()


_TELEMETRY = LLMTelemetry()


def get_telemetry() -> LLMTelemetry:
    """进程级遥测实例（组件默认使用它）。"""
    return _TELEMETRY
