"""所有客户端共享的进程级限制；缩小额度时不替换正在使用的锁。"""
import threading
import time
from contextlib import contextmanager

from app.llm.errors import BudgetExceeded

_condition = threading.Condition()
_limit = 4
_active = 0


def configure_limit(limit: int):
    global _limit
    if limit < 1:
        raise ValueError("并发限制必须为正数")
    with _condition:
        _limit = limit
        _condition.notify_all()


def snapshot():
    with _condition:
        return {"limit": _limit, "active": _active, "scope": "process"}


@contextmanager
def slot(timeout: float):
    global _active
    deadline = time.monotonic() + timeout
    with _condition:
        while _active >= _limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BudgetExceeded("模型请求繁忙，请稍后重试")
            _condition.wait(remaining)
        _active += 1
    try:
        yield
    finally:
        with _condition:
            _active -= 1
            _condition.notify_all()
