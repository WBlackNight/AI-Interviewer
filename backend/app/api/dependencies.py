"""Shared HTTP dependencies for account authentication work."""
from fastapi import HTTPException, Request
from app.services.accounts import AuthThrottle

throttle = AuthThrottle()


def auth_work(request: Request):
    # 不信任客户端X-Forwarded-For，反代部署另配可信代理和分布式配额。
    throttle.check(request.client.host if request.client else "unknown")
    if not throttle.work.acquire(blocking=False):
        raise HTTPException(429, "登录服务繁忙，请稍后再试")
    try:
        yield
    finally:
        throttle.work.release()

