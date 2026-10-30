"""FastAPI 应用入口。

启动：cd backend && uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.ws import router as ws_router
from app.api.realtime import router as realtime_router
from app.api.accounts import router as accounts_router
from app.api.question_marks import router as question_marks_router
from app.api.preparation import router as preparation_router
from app.api.account_profile import router as profile_router
from app.config import get_settings
from app.db import SessionLocal, engine
from app.factories import load_assets
from app.models.entities import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        on_startup()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI 模拟面试官 —— 传智杯 AI Web 赛道参赛项目",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(ws_router)
    app.include_router(realtime_router)
    app.include_router(accounts_router)
    app.include_router(question_marks_router)
    app.include_router(preparation_router)
    app.include_router(profile_router)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/auth/", "/api/account", "/api/interview", "/api/resume")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith(("/api/auth/", "/api/account")):
            fields={str(error['loc'][-1]) for error in exc.errors()}
            detail=('请输入有效的邮箱地址' if 'email' in fields else '昵称应为1–32个可见字符' if 'nickname' in fields else '请填写有效的验证码' if fields & {'captcha_id','captcha_code','code','challenge_id'} else '账户输入格式不正确，请检查用户名及密码长度（12–128字符）')
            return JSONResponse({'detail':detail},status_code=422)
        return await request_validation_exception_handler(request, exc)

    def on_startup() -> None:
        # 开发期自动建表；生产用 alembic 迁移（见 README 路线图）
        Base.metadata.create_all(bind=engine)
        from app.migrations import upgrade_event_sequences, upgrade_interview_user_nullable
        # 顺序：先补 schema（列可空性），再修历史数据（事件序号）。
        upgrade_interview_user_nullable(engine)
        upgrade_event_sequences(engine)
        # P2 步骤 2.1：严格模式（模型失败即抛错而非回退）只应在开发期开启。
        from app.llm.resilience import configure_strict

        configure_strict(settings.llm_strict_mode)
        from app.llm.limiter import configure_limit
        configure_limit(settings.llm_max_concurrency)
        # P2 步骤 2.2：评分缓存默认关闭；开启后进程级共享（注意 build_scorer
        # 是每轮新建的，缓存若挂在实例上就永远不会命中）。
        from app.agent.score_cache import configure_cache

        configure_cache(
            enabled=settings.scoring_cache_enabled,
            max_entries=settings.scoring_cache_max_entries,
            ttl_seconds=settings.scoring_cache_ttl_seconds,
        )
        from app.repositories import seed_questions

        trees, bank = load_assets(settings)
        db = SessionLocal()
        try:
            added = seed_questions(db, bank.questions)
        finally:
            db.close()
        logging.getLogger(__name__).info(
            "启动完成：题库 %d 题（新增 %d），LLM=%s，沙箱=%s",
            len(bank),
            added,
            "on" if settings.llm_api_key else "off",
            "on" if settings.judge0_url else "off",
        )

    return app


app = create_app()
