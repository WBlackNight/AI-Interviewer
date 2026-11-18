"""Shared response headers and validation messages for every REST route."""
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
import logging
import uuid


def register_http_policy(app):
    @app.middleware("http")
    async def private_responses(request, call_next):
        is_admin_request = request.url.path.startswith('/api/admin')
        if is_admin_request:
            request.state.admin_request_id = uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception as error:
            if not is_admin_request:
                raise
            logging.getLogger(__name__).error('Admin request failed id=%s type=%s', request.state.admin_request_id, type(error).__name__)
            response = JSONResponse({'detail': '管理服务暂时不可用，请稍后重试。'}, status_code=500)
        if is_admin_request:
            response.headers['X-Request-ID'] = request.state.admin_request_id
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith(("/api/auth/", "/api/account", "/api/interview", "/api/resume", "/api/shared-report", "/api/assistant", "/api/admin", "/api/forum")):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path in ("/share", "/share.html", "/api/shared-report", "/admin", "/admin.html"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith('/api/forum'):
            return JSONResponse({'detail': '请检查社区表单内容、长度或筛选参数。'}, status_code=422)
        if request.url.path.startswith('/api/admin'):
            fields = {str(error['loc'][-1]) for error in exc.errors()}
            detail = ('请选择有效的日期范围。' if fields & {'start', 'end'} else
                      '审校输入无效：备注最多500字；需修改的题目请填写至少5字说明，并重新读取最新版本。'
                      if '/review' in request.url.path else '筛选条件无效，请检查状态、排序或分页范围。')
            return JSONResponse({'detail': detail}, status_code=422)
        if request.url.path.startswith('/api/assistant'):
            return JSONResponse({'detail': '请检查输入：消息为1–1200字，请选择可用方向并刷新后重试。'}, status_code=422)
        if request.url.path.startswith(("/api/auth/", "/api/account")):
            fields={str(error['loc'][-1]) for error in exc.errors()}
            if fields & {'gender', 'age', 'bio', 'expected_version'} and request.url.path == '/api/account/profile':
                return JSONResponse({'detail': '请检查资料：年龄填写1至120的整数，简介最多160字，性别也可留空'}, status_code=422)
            if 'target_sessions' in fields:
                return JSONResponse({'detail': '阶段目标请填写1至50场，或留空取消目标'}, status_code=422)
            if fields & {'hours', 'scope'}:
                return JSONResponse({'detail': '请选择有效的分享范围和有效期'}, status_code=422)
            if 'email' in fields:
                detail = '请输入有效的邮箱地址'
            elif 'nickname' in fields:
                detail = '昵称应为1–32个可见字符'
            elif fields & {'captcha_id', 'captcha_code', 'code', 'challenge_id'}:
                detail = '请填写有效的验证码'
            else:
                detail = '账户输入格式不正确，请检查用户名及密码长度（8–128字符）'
            return JSONResponse({'detail':detail},status_code=422)
        if request.url.path.startswith("/api/"):
            errors = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
            return JSONResponse({"detail": errors}, status_code=422)
        return await request_validation_exception_handler(request, exc)

