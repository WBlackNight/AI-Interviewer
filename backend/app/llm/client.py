"""LLM 客户端：OpenAI 兼容协议（DeepSeek / GLM / Qwen / 本地 vLLM 均可接入）。

统一薄封装，供 Scorer / Prober / Planner / 简历解析复用。
未配置密钥时工厂返回 None，上层自动使用启发式实现（见 factories.py）。

P2 步骤 2.1 加固点：
- **有限重试**，且只重试可重试类别（超时/429/5xx/网络）。4xx 与密钥错误
  重试不仅无用，还会把"配置错误"伪装成"偶发故障"；
- **并发上限**：组件在工作线程中同步调用，这里用信号量限制在飞请求数，
  避免批量评测时把供应商打爆或触发限流；
- **预算记账**：token 数取自响应 usage（事实），金额仅在运维配置单价表时计算；
- **错误分类**：所有失败统一抛 ``LLMError``，便于上层区分处理。

重试使用阻塞式 ``time.sleep``：调用发生在 ``asyncio.to_thread`` 的工作线程里，
不占用事件循环；重试次数少、退避短，可接受。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from app.llm.budget import current_budget
from app.llm.errors import BudgetExceeded, LLMError, LLMErrorKind, as_llm_error, classify_exception
from app.llm.limiter import slot

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str: ...


def _extract_usage(response) -> tuple[int, int] | None:
    """从响应取有限非负整数用量；缺失/非法返回None，不伪造免费调用。"""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
        return None
    return prompt, completion


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.3,
        timeout: float = 60.0,
        max_attempts: int = 3,
        max_concurrency: int = 4,
        backoff_base_seconds: float = 0.5,
        max_output_tokens: int = 2048,
        thinking_mode: str | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须 >= 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency 必须 >= 1")
        from openai import OpenAI  # 延迟导入：未配置密钥时不强制安装可用性
        import httpx

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0,
            http_client=httpx.Client(trust_env=False, follow_redirects=False))
        self._model = model
        self._default_temperature = temperature
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._queue_timeout = timeout
        self._usage_lock = threading.Lock()
        self._tokens_in = 0
        self._tokens_out = 0
        self._network_calls = 0
        self._unknown_usage_calls = 0
        self._max_output_tokens = max_output_tokens
        self._thinking_mode = thinking_mode

    # -- 生命周期 --------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    @property
    def model(self) -> str:
        return self._model

    @property
    def usage(self) -> dict:
        with self._usage_lock:
            return {"tokens_in": self._tokens_in, "tokens_out": self._tokens_out}

    @property
    def attempts_allowed(self) -> int:
        return self._max_attempts

    def usage_diagnostics(self) -> dict:
        with self._usage_lock:
            return {"tokens_in": self._tokens_in, "tokens_out": self._tokens_out,
                    "network_calls": self._network_calls,
                    "unknown_usage_calls": self._unknown_usage_calls, "currency_cost": None}

    # -- 调用 ------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        content, tokens_in, tokens_out = self._call_with_retry(
            messages, json_mode=json_mode, temperature=temperature
        )
        return content

    def _settle(self, budget, call_id, usage):
        with self._usage_lock:
            if usage is not None:
                self._tokens_in += usage[0]
                self._tokens_out += usage[1]
            else:
                self._unknown_usage_calls += 1
        if budget is None:
            return
        if hasattr(budget, "finish_call"):
            try:
                budget.finish_call(call_id, usage)
            except BudgetExceeded:
                raise
            except Exception:
                raise BudgetExceeded("用量结算失败，预算已暂停，请核对账本") from None
        elif usage is not None:
            budget.charge(tokens_in=usage[0], tokens_out=usage[1])
        elif budget.enabled:
            raise BudgetExceeded("模型未返回有效usage，无法确认预算")

    def _call_with_retry(
        self, messages: list[dict], *, json_mode: bool, temperature: float | None
    ) -> tuple[str, int, int]:
        last_error: LLMError | None = None
        for attempt in range(1, self._max_attempts + 1):
            budget = current_budget()
            call_id = None
            attempted = False
            try:
                with slot(self._queue_timeout):
                    if budget is not None:
                        if hasattr(budget, "begin_call"):
                            call_id = budget.begin_call()
                        else:
                            budget.check()
                    attempted = True
                    with self._usage_lock:
                        self._network_calls += 1
                    extension = ({"extra_body": {"thinking": {"type": self._thinking_mode}}}
                                 if self._thinking_mode is not None else {})
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,  # type: ignore[arg-type]
                        temperature=(
                            self._default_temperature if temperature is None else temperature
                        ),
                        response_format=(
                            {"type": "json_object"} if json_mode else None  # type: ignore[arg-type]
                        ),
                        max_tokens=self._max_output_tokens,
                        **extension,
                    )
            except BudgetExceeded:
                raise
            except Exception as exc:
                if not attempted and budget is not None:
                    raise BudgetExceeded("预算检查失败，请核对账本后重试") from None
                error = as_llm_error(exc)
                if attempted:
                    try:
                        self._settle(budget, call_id, None)
                    except BudgetExceeded as paused:
                        # 未知用量仍暂停预算，同时保留固定供应商错误类别供诊断。
                        paused.provider_kind = error.kind
                        raise paused from None
                last_error = error
                if error.retryable and attempt < self._max_attempts:
                    delay = self._backoff_base * (2 ** (attempt - 1))
                    logger.info(
                        "llm_retry attempt=%d/%d kind=%s delay_s=%.2f",
                        attempt, self._max_attempts, error.kind.value, delay,
                    )
                    time.sleep(delay)
                    continue
                raise error from None

            usage = _extract_usage(response)
            self._settle(budget, call_id, usage)
            try:
                choice = response.choices[0]
                content = choice.message.content
            except (AttributeError, IndexError, TypeError):
                raise LLMError(LLMErrorKind.BAD_PAYLOAD, "模型响应结构不完整") from None
            if getattr(choice, "finish_reason", "stop") != "stop":
                raise LLMError(LLMErrorKind.BAD_PAYLOAD, "模型响应未正常完成") from None
            tokens_in, tokens_out = usage or (0, 0)
            if content is None or not str(content).strip():
                # 空内容可能是瞬时故障，按可重试处理。
                last_error = LLMError(LLMErrorKind.EMPTY_RESPONSE, "模型返回空内容")
                if attempt < self._max_attempts:
                    time.sleep(self._backoff_base * (2 ** (attempt - 1)))
                    continue
                raise last_error
            return str(content), tokens_in, tokens_out

        # 理论上不可达：循环要么 return 要么 raise。
        raise last_error or LLMError(LLMErrorKind.UNKNOWN, "调用失败且无错误详情")


def classify(exc: BaseException) -> LLMErrorKind:
    """便捷入口（供诊断脚本与测试使用）。"""
    return classify_exception(exc)
