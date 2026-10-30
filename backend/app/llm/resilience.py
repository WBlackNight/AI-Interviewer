"""组件回退策略（P2 步骤 2.1）。

所有"LLM 失败 → 启发式兜底"的组件都走这里，保证三件事一致：

1. **回退可观察**：每次调用都记录 `llm_success / heuristic_fallback / error_raised`，
   结构化日志含组件名与错误类别。评审要求"网络失败不得把启发式结果标成
   LLM 验证成功"——靠的就是这条统一记录，而不是各组件各写一份 try/except。
2. **预算是策略性中止，不是供应商故障**：``BudgetExceeded`` 直接向上抛，
   **绝不**回退。否则"超预算"会静默变成"继续花钱跑启发式"，保护形同虚设。
3. **严格模式**：开发期可让回退直接变成异常，避免静默回退掩盖缺陷。

严格模式的开关用模块级配置而非构造参数：组件在工厂里被大量实例化，
若走构造参数就得给每个组件都加一条线，反而更容易漏掉某一个。
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from app.llm.budget import current_budget
from app.llm.errors import BudgetExceeded, LLMError, LLMErrorKind, as_llm_error, classify_exception
from app.llm.telemetry import CallOutcome, LLMTelemetry, get_telemetry

T = TypeVar("T")

_strict = False


def configure_strict(enabled: bool) -> None:
    """由应用启动时按配置调用一次。"""
    global _strict
    _strict = bool(enabled)


def strict_enabled() -> bool:
    return _strict


def call_with_fallback(
    *,
    component: str,
    primary: Callable[[], T],
    fallback: Callable[[], T] | None = None,
    telemetry: LLMTelemetry | None = None,
    strict: bool | None = None,
    on_success: Callable[[T], None] | None = None,
) -> T:
    """执行 ``primary``，失败时按配置回退或抛出。

    ``component`` 用于遥测与日志分组（如 ``scorer`` / ``prober`` / ``planner`` /
    ``resume_parser``），必须是稳定的小写标识。

    ``on_success`` 只在**模型成功**时回调。评分缓存必须挂在这里：
    若在函数返回后无条件写缓存，一次偶发失败产生的启发式结果会被固化，
    把短暂的降级变成长期的劣化。
    """
    telemetry = telemetry or get_telemetry()
    strict = strict_enabled() if strict is None else strict

    budget = current_budget()
    tokens_before = budget.used_tokens if budget is not None else 0
    started = time.monotonic()
    try:
        value = primary()
    except BudgetExceeded as exc:
        # 策略性中止：记账后立即上抛，不记录为"回退"。
        telemetry.record(component, CallOutcome.ERROR_RAISED,
                         latency_ms=(time.monotonic() - started) * 1000.0,
                         error_kind=exc.provider_kind or LLMErrorKind.BUDGET_EXCEEDED)
        raise
    except BaseException as exc:  # noqa: BLE001 - 需要分类所有失败
        error = as_llm_error(exc)
        elapsed = (time.monotonic() - started) * 1000.0
        # primary 内部可能已经完成计费（例如拿到响应后校验失败）。
        charged = (budget.used_tokens - tokens_before) if budget is not None else 0
        telemetry.record(
            component,
            CallOutcome.ERROR_RAISED if strict else CallOutcome.HEURISTIC_FALLBACK,
            latency_ms=elapsed,
            error_kind=error.kind,
            detail=error.detail,
            tokens_in=charged,
        )
        if strict:
            raise error from None
        if fallback is None:
            raise
        return fallback()

    elapsed = (time.monotonic() - started) * 1000.0
    charged = (budget.used_tokens - tokens_before) if budget is not None else 0
    telemetry.record(
        component, CallOutcome.LLM_SUCCESS, latency_ms=elapsed, tokens_in=charged
    )
    if on_success is not None:
        on_success(value)
    return value


def handle_fallback(
    *,
    component: str,
    exc: BaseException,
    fallback: Callable[[], T],
    telemetry: LLMTelemetry | None = None,
    strict: bool | None = None,
    latency_ms: float = 0.0,
) -> T:
    """``except`` 分支里的统一回退入口。

    与 ``call_with_fallback`` 是**同一套策略的两个入口**：
    主体逻辑已经写成 try/except（且体量大、已充分测试）时，
    在 except 里调这个即可，不必为了统一入口去重排整段代码——
    改动面越小，回归风险越低。

    预算超限**穿透**：``BudgetExceeded`` 是我们的策略性中止，
    必须继续上抛，不能被回退吞掉（否则预算保护会静默失效）。
    """
    telemetry = telemetry or get_telemetry()
    if isinstance(exc, BudgetExceeded):
        telemetry.record(component, CallOutcome.ERROR_RAISED, latency_ms=latency_ms,
                         error_kind=exc.provider_kind or LLMErrorKind.BUDGET_EXCEEDED)
        raise exc
    strict = strict_enabled() if strict is None else strict
    error = as_llm_error(exc)
    telemetry.record(
        component,
        CallOutcome.ERROR_RAISED if strict else CallOutcome.HEURISTIC_FALLBACK,
        latency_ms=latency_ms,
        error_kind=error.kind,
        detail=error.detail,
    )
    if strict:
        raise error from None
    return fallback()


def record_success(component: str, *, latency_ms: float = 0.0,
                   telemetry: LLMTelemetry | None = None) -> None:
    """记录一次成功的真实调用。

    **必须与 ``handle_fallback`` 配对使用**：``handle_fallback`` 只在
    ``except`` 分支被调用，如果成功路径不记录，该组件在遥测里会完全没有条目，
    被诊断为 ``not_run``——把"一直好用"误报成"从未运行"。
    这是本模块引入后由测试发现的一个真实缺陷（见 docs/错误经验总结.md）。
    """
    (telemetry or get_telemetry()).record(
        component, CallOutcome.LLM_SUCCESS, latency_ms=latency_ms
    )


def describe_outcome(component: str) -> dict:
    """取某组件的当前统计（供诊断接口与 llm_ping 使用）。"""
    return get_telemetry().snapshot().get(component, {})


__all__ = [
    "BudgetExceeded",
    "LLMError",
    "call_with_fallback",
    "classify_exception",
    "configure_strict",
    "describe_outcome",
    "handle_fallback",
    "record_success",
    "strict_enabled",
]
