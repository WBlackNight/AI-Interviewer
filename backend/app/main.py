"""FastAPI 应用入口。

启动：cd backend && uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    from app.api.practice_config import router as practice_config_router
    app.include_router(practice_config_router)
    from app.api.account_recovery import router as recovery_router
    app.include_router(recovery_router)
    from app.api.report_shares import router as shares_router
    app.include_router(shares_router)
    from app.api.assistant import router as assistant_router
    app.include_router(assistant_router)
    from app.api.admin import router as admin_router
    app.include_router(admin_router)
    from app.api.forum import router as forum_router
    app.include_router(forum_router)

    from app.api.frontend import attach_frontend
    attach_frontend(app)

    from app.api.http_policy import register_http_policy
    register_http_policy(app)

    def on_startup() -> None:
        # 建表、旧库升级与版本登记共享数据库锁和事务。
        from app.schema_versions import upgrade_schema
        upgrade_schema(engine)
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
