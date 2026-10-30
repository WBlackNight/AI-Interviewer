"""LLM 错误分类（P2 步骤 2.1）。

评审要求："组件捕获供应商错误时输出结构化日志/指标"，以及
**"网络失败不把启发式结果标成'LLM 验证成功'"**。
要做到这一点，必须先能把失败**分类**，否则日志里只有一句
无差别的 `reason=Exception`，无法区分"供应商超时"和"模型输出格式错"。

设计说明：按**异常类名**而非类型判断，避免在模块顶层硬依赖 openai
（未配置密钥时不应强制要求安装可用性）。代价是类名匹配较松，
因此对已知状态码优先用 status_code 判断，类名只作兜底。
"""
from __future__ import annotations

from enum import Enum


class LLMErrorKind(str, Enum):
    TIMEOUT = "timeout"              # 请求超时
    AUTH = "auth"                    # 密钥无效 / 无权限
    RATE_LIMIT = "rate_limit"        # 429
    SERVER = "server"                # 5xx
    BAD_REQUEST = "bad_request"      # 4xx（请求本身不合法，重试无用）
    NETWORK = "network"              # 连接失败 / DNS / 断流
    EMPTY_RESPONSE = "empty_response"  # 返回空内容
    BAD_PAYLOAD = "bad_payload"      # 输出不是合法 JSON / 字段类型错 / 校验不通过
    BUDGET_EXCEEDED = "budget_exceeded"
    UNKNOWN = "unknown"


#: 可重试类别。注意 BAD_REQUEST / AUTH / BAD_PAYLOAD **不可重试**——
#: 重试只会浪费时间与配额，还会把"配置错误"伪装成"偶发故障"。
RETRYABLE_KINDS = frozenset({
    LLMErrorKind.TIMEOUT,
    LLMErrorKind.RATE_LIMIT,
    LLMErrorKind.SERVER,
    LLMErrorKind.NETWORK,
})

# 仅这些固定原因可进入遥测；模型字段值、原回答和供应商正文不得进入日志。
VALIDATION_REASONS = frozenset({
    "quote_not_in_answer", "quote_anchor_mismatch", "anchor_set_mismatch",
    "hit_without_quote", "anchor_overlap", "score_json_invalid",
    "score_schema_payload", "score_schema_score", "score_schema_dimensions",
    "score_schema_key_points_hit", "score_schema_key_points_missed",
    "score_schema_evidence", "score_schema_evidence_quotes",
    "score_quotes_missing", "score_quotes_list", "score_quotes_item",
    "score_quotes_count", "score_quotes_shape", "score_quotes_empty", "score_quotes_limit",
})

_BY_NAME = {
    "APITimeoutError": LLMErrorKind.TIMEOUT,
    "Timeout": LLMErrorKind.TIMEOUT,
    "TimeoutError": LLMErrorKind.TIMEOUT,
    "ReadTimeout": LLMErrorKind.TIMEOUT,
    "AuthenticationError": LLMErrorKind.AUTH,
    "PermissionDeniedError": LLMErrorKind.AUTH,
    "RateLimitError": LLMErrorKind.RATE_LIMIT,
    "InternalServerError": LLMErrorKind.SERVER,
    "APIStatusError": LLMErrorKind.SERVER,
    "BadRequestError": LLMErrorKind.BAD_REQUEST,
    "UnprocessableEntityError": LLMErrorKind.BAD_REQUEST,
    "APIConnectionError": LLMErrorKind.NETWORK,
    "ConnectError": LLMErrorKind.NETWORK,
    "ConnectionError": LLMErrorKind.NETWORK,
}

_STATUS_KINDS = {
    400: LLMErrorKind.BAD_REQUEST,
    401: LLMErrorKind.AUTH,
    403: LLMErrorKind.AUTH,
    404: LLMErrorKind.BAD_REQUEST,
    422: LLMErrorKind.BAD_REQUEST,
    429: LLMErrorKind.RATE_LIMIT,
}


class LLMError(RuntimeError):
    """带分类的模型调用错误。"""

    def __init__(self, kind: LLMErrorKind, detail: str, *, status: int | None = None) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS


class BudgetExceeded(RuntimeError):
    """用量/成本预算耗尽。

    刻意**不**继承 ``LLMError``：预算是我们自己的策略性中止，
    不是供应商故障，绝不能落到"回退到启发式"的分支里被吞掉——
    否则预算保护会静默失效。
    """

    def __init__(self, detail: str, *, provider_kind: LLMErrorKind | None = None) -> None:
        super().__init__(detail)
        self.provider_kind = provider_kind


def classify_exception(exc: BaseException) -> LLMErrorKind:
    """把任意异常归类。已分类的直接返回其类别。"""
    if isinstance(exc, LLMError):
        return exc.kind
    if isinstance(exc, BudgetExceeded):
        return LLMErrorKind.BUDGET_EXCEEDED
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        # 约定：组件内对模型输出的解析/校验失败统一抛 ValueError 家族。
        return LLMErrorKind.BAD_PAYLOAD

    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status >= 500:
            return LLMErrorKind.SERVER
        if status in _STATUS_KINDS:
            return _STATUS_KINDS[status]

    for klass in type(exc).__mro__:
        if klass.__name__ in _BY_NAME:
            return _BY_NAME[klass.__name__]
    return LLMErrorKind.UNKNOWN


def as_llm_error(exc: BaseException) -> LLMError:
    """把异常规整为 ``LLMError``（幂等）。"""
    if isinstance(exc, LLMError):
        return exc
    status = getattr(exc, "status_code", None)
    reason = "供应商请求或输出校验失败（原始详情不记录）"
    # 仅将项目内固定校验消息映射到固定代码，不记录动态锚点、片段或供应商正文。
    if isinstance(exc, ValueError):
        known = {
            "LLM 输出中未找到 JSON": "score_json_invalid",
            "同一要点不能既命中又缺失": "anchor_overlap",
            "评分引用不属于原回答": "quote_not_in_answer",
            "引用未映射到任何评分锚点": "quote_anchor_mismatch",
            "评分锚点不属于当前题": "anchor_set_mismatch",
            "命中的要点没有任何引用支撑": "hit_without_quote",
        }
        reason = next((code for prefix, code in known.items() if str(exc).startswith(prefix)), reason)
        if str(exc) in VALIDATION_REASONS:
            reason = str(exc)
    return LLMError(
        classify_exception(exc),
        # 供应商正文/ValidationError可能包含输入或密钥，日志只允许固定类别。
        reason,
        status=status if isinstance(status, int) else None,
    )
