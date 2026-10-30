"""REST：简历上传 / 面试创建 / 报告查询 / 健康检查。"""
from __future__ import annotations
import os
import uuid
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, sessionmaker
from app.llm.budget import use_budget
from app.llm.persistent_budget import PersistentBudget, usage_snapshot
from app.llm.errors import BudgetExceeded
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_db
from app.domain import PlanItem, ResumeData
from app.factories import build_llm, build_planner, load_assets
from app.rag.resume_parser import parse_resume_text, parse_resume_text_with_llm
from app.repositories import (
    create_user_with_resume,
    get_interview,
    get_resume,
    cancel_interview, ConcurrentTurnError,
)
from app.schemas import (
    HealthResponse,
    InterviewCreateRequest,
    InterviewCreateResponse,
    ResumeCreateRequest,
    ResumeResponse,
    InterviewCancelResponse,
)
from app.services.report import build_report
from app.services.catalog import question_catalog
from app.services.coverage import catalog_coverage
from app.services.question_audit import load_registry
from app.services.practice import available_themes, practice_plan, weak_practice_themes
from app.models.entities import Account, ResourceOwner
from app.services.accounts import optional_account, attach_owner, lock_account
from app.services.history import summaries
from app.services.interviews import save_interview as _save_interview
from app.security import issue_access, has_access, sanitize_pii

router = APIRouter(prefix="/api", tags=["core"])
settings = get_settings()


@router.get("/diagnostics/sandbox")
def sandbox_diagnostics():
    from app.sandbox.admission import admission
    return {"configured":bool(settings.judge0_url), "execution_verified":False,
            "admission":admission.snapshot(), "note":"配置和本机准入状态不证明远端执行或隔离有效"}


@router.get("/voice/config")
def voice_config():
    """公开能力标记，不返回密钥、端点凭据或任何供应商原始消息。"""
    return {"enabled": settings.voice_enabled,
            "realtime_enabled": settings.voice_enabled and settings.voice_asr_provider == settings.voice_tts_provider == 'doubao',
            "asr_provider": settings.voice_asr_provider, "tts_provider": settings.voice_tts_provider,
            "input_rate": 16000, "output_rate": 24000, "format": "pcm_s16le",
            "max_seconds": min(settings.voice_max_utterance_seconds, settings.doubao_voice_session_seconds),
            "demo_only": "dummy" in (settings.voice_asr_provider, settings.voice_tts_provider),
            "quality_verified": False}


@router.get("/diagnostics/voice")
def voice_diagnostics():
    from app.voice.doubao import diagnostics
    configured = bool(settings.doubao_voice_app_id and settings.doubao_voice_access_token) if settings.doubao_voice_auth_mode == 'legacy' else bool(settings.doubao_voice_api_key)
    return {**voice_config(), **diagnostics(), "auth_mode": settings.doubao_voice_auth_mode,
            "configured": configured,
            "note": "配置不等于服务可用；语音用量不计入文本LLM token预算，无内置费用估算"}


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    from app.models.entities import Question as QuestionORM

    trees, bank = load_assets(settings)
    question_count = len(bank)
    return HealthResponse(
        process_id=os.getpid(),
        status="ok",
        app_name=settings.app_name,
        llm_enabled=bool(settings.llm_api_key),
        sandbox_enabled=bool(settings.judge0_url),
        question_count=question_count,
    )


@router.get("/diagnostics/llm")
def llm_diagnostics() -> dict:
    """LLM 组件回退与用量诊断（P2 步骤 2.1）。

    为什么需要它：``/api/health`` 里的 ``llm_enabled`` **只说明"配置存在"**，
    说明不了任何一次调用成功过。真实可用性必须看这里的分项计数
    （``llm_success`` vs ``heuristic_fallback``）。

    只暴露计数、类别与配置项；**不含**回答、简历、凭据或完整 URL。
    """
    from urllib.parse import urlparse

    from app.agent.score_cache import get_score_cache
    from app.llm.resilience import strict_enabled
    from app.llm.telemetry import get_telemetry
    from app.llm.limiter import snapshot as limiter_snapshot

    host = urlparse(settings.llm_base_url).hostname or "unknown"
    configured = bool(settings.llm_api_key)
    return {
        "llm_configured": configured,
        "strict_mode": strict_enabled(),
        "provider_host": host if configured else None,
        "model": settings.llm_model if configured else None,
        "max_attempts": settings.llm_max_attempts,
        "max_concurrency": settings.llm_max_concurrency,
        "concurrency": limiter_snapshot(),
        "components": get_telemetry().snapshot(),
        "score_cache": {
            **get_score_cache().stats(),
            "enabled": get_score_cache().active,
            "note": (
                "默认关闭。命中缓存的两次评测没有调用模型，"
                "不能作为可重复性证据。"
            ),
        },
        "budget": {
            "limit_tokens": settings.llm_budget_tokens_per_interview,
            "limit_cost": settings.llm_budget_cost_per_interview,
            "prices_configured": (
                settings.llm_price_input_per_million is not None
                and settings.llm_price_output_per_million is not None
            ),
        },
        "note": "计数为进程内累加，仅覆盖本次进程生命周期；不是指标后端。",
    }


@router.get("/diagnostics/retrieval")
def retrieval_diagnostics() -> dict:
    _, bank = load_assets(settings)
    return {**bank.diagnostics(), "question_count": len(bank),
            "note": "hash为离线词法基线，不是语义模型；计数只覆盖当前进程缓存生命周期"}


@router.post("/resume", response_model=ResumeResponse)
def create_resume(payload: ResumeCreateRequest, db: Session = Depends(get_db),
                  account: Account | None = Depends(optional_account)) -> ResumeResponse:
    if not payload.resume_text.strip():
        raise HTTPException(status_code=422, detail="简历文本不能为空")
    account_id = account.id if account else None
    db.rollback()  # 账户依赖的读取不跨模型解析持有事务。

    safe_text = sanitize_pii(payload.resume_text)
    safe_name = sanitize_pii(payload.name)
    resume_id = uuid.uuid4().hex
    llm = build_llm(settings)
    try:
        meter = PersistentBudget(sessionmaker(bind=db.get_bind()), "resume", resume_id, settings) if llm else None
        with use_budget(meter):
            resume_data: ResumeData = (
                parse_resume_text_with_llm(safe_text, llm)
                if llm else parse_resume_text(safe_text)
            )
    except BudgetExceeded:
        raise HTTPException(429, detail="简历模型预算已暂停或耗尽，请核对用量") from None
    finally:
        if hasattr(llm, "close"):
            llm.close()
    if account_id:
        lock_account(db, account_id)
    resume = create_user_with_resume(
        db,
        name=safe_name,
        resume_text=safe_text,
        structured={
            "skills": resume_data.skills,
            "projects": resume_data.projects,
            "education": resume_data.education,
        },
        commit=False,
        resume_id=resume_id,
    )
    token = None if account_id else issue_access(db, "resume", resume.id)
    if account_id:
        attach_owner(db, "resume", resume.id, account_id)
    db.commit()
    return ResumeResponse(
        access_token=token,
        account_owned=account_id is not None,
        resume_id=resume.id,
        user_id=resume.user_id,
        skills=resume_data.skills,
        projects=resume_data.projects,
        education=resume_data.education,
    )


@router.get("/resume/limits")
def resume_limits() -> dict:
    return {
        "pdf_max_bytes": settings.resume_pdf_max_bytes,
        "pdf_max_pages": settings.resume_pdf_max_pages,
        "text_max_chars": settings.resume_pdf_max_text_chars,
        "ocr_supported": False,
    }


@router.post("/resume/pdf", response_model=ResumeResponse, openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "required": ["file"], "properties": {
            "file": {"type": "string", "format": "binary"},
            "name": {"type": "string", "maxLength": 64, "default": "匿名用户"},
        }},
    }}},
})
async def create_resume_pdf(request: Request, db: Session = Depends(get_db),
                            account: Account | None = Depends(optional_account)) -> ResumeResponse:
    from app.api.resume_upload import read_pdf_upload
    from app.rag.pdf_extractor import PDFError, ERRORS, extract_pdf_text

    upload = await read_pdf_upload(request, max_bytes=settings.resume_pdf_max_bytes,
                                   timeout_seconds=settings.resume_upload_timeout_seconds)
    try:
        name = bytes(upload.name).decode("utf-8") or "匿名用户"
    except UnicodeDecodeError:
        raise HTTPException(422, "姓名字段必须为 UTF-8 文本") from None
    if len(name) > 64:
        raise HTTPException(422, "姓名最多64个字符")
    try:
        text = await run_in_threadpool(
            extract_pdf_text, bytes(upload.data),
            max_pages=settings.resume_pdf_max_pages,
            max_chars=settings.resume_pdf_max_text_chars,
            timeout_seconds=settings.resume_pdf_timeout_seconds,
        )
    except PDFError as exc:
        status, detail = ERRORS[exc.code]
        raise HTTPException(status, detail=detail,
                            headers={"Retry-After": "2"} if status == 429 else None) from None
    finally:
        upload.data.clear()
    # 统一经过文本接口的脱敏、LLM/规则解析、资源授权和单次事务保存。
    return await run_in_threadpool(create_resume, ResumeCreateRequest(name=name, resume_text=text), db, account)


@router.post("/interview", response_model=InterviewCreateResponse)
def create_interview_api(
    payload: InterviewCreateRequest, db: Session = Depends(get_db),
    resume_token: str | None = Header(default=None, alias="X-Resume-Token"),
    account: Account | None = Depends(optional_account),
) -> InterviewCreateResponse:
    trees, bank = load_assets(settings)
    tree = trees.get(payload.position)
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail=f"暂不支持岗位 {payload.position}，当前支持：{list(trees)}",
        )

    if payload.themes is not None:
        if payload.resume_id:
            raise HTTPException(422, detail="主题专项无需简历，请移除resume_id")
        try:
            plan = practice_plan(tree, bank, payload.position, payload.difficulty,
                                 payload.themes, settings.max_plan_themes)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from None
        return _save_interview(db, payload.position, payload.difficulty, plan,
                               account_id=account.id if account else None)

    resume_data = ResumeData()
    user_id: str | None = None
    account_id = account.id if account else None
    if payload.resume_id:
        if not has_access(db, "resume", payload.resume_id, resume_token):
            raise HTTPException(status_code=403, detail="简历访问凭据无效")
        resume = get_resume(db, payload.resume_id)
        if resume is None:
            raise HTTPException(status_code=404, detail="简历不存在")
        user_id = resume.user_id  # 关联用户，便于后续能力画像沉淀
        owner = db.get(ResourceOwner, ("resume", payload.resume_id))
        if owner:
            if account and account.id != owner.account_id:
                raise HTTPException(403, detail="简历不属于当前登录账户")
            account_id = owner.account_id
        structured = resume.structured or {}
        resume_data = ResumeData(
            skills=list(structured.get("skills", [])),
            projects=list(structured.get("projects", [])),
            education=str(structured.get("education", "")),
        )

    db.rollback()  # 不跨模型调用持有业务读事务，计费使用独立事务。
    interview_id = uuid.uuid4().hex
    llm = build_llm(settings)
    planner = build_planner(settings, llm, tree)
    try:
        meter = PersistentBudget(sessionmaker(bind=db.get_bind()), "interview", interview_id, settings) if llm else None
        with use_budget(meter):
            plan = planner.build_plan(
                position=payload.position, difficulty=payload.difficulty,
                resume=resume_data, bank=bank, max_themes=settings.max_plan_themes,
            )
    except BudgetExceeded:
        raise HTTPException(429, detail="规划模型预算已暂停或耗尽，请核对用量") from None
    finally:
        if hasattr(llm, "close"):
            llm.close()
    if not plan:
        raise HTTPException(status_code=500, detail="面试大纲生成失败（题库为空？）")

    return _save_interview(db, payload.position, payload.difficulty, plan,
                           user_id=user_id, resume_id=payload.resume_id, interview_id=interview_id,
                           account_id=account_id)


@router.post("/interview/{interview_id}/cancel", response_model=InterviewCancelResponse)
def cancel_interview_api(interview_id: str, db: Session = Depends(get_db),
                         token: str | None = Header(default=None, alias="X-Interview-Token")):
    if not has_access(db, "interview", interview_id, token):
        raise HTTPException(403, detail="面试访问凭据无效")
    interview = get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(404, detail="面试不存在")
    try:
        changed, version = cancel_interview(db, interview)
    except (ConcurrentTurnError, ValueError) as exc:
        db.rollback()
        raise HTTPException(409, detail=str(exc)) from None
    return InterviewCancelResponse(interview_id=interview_id, changed=changed,
        version=version, report_url=f"/report/{interview_id}")


@router.get("/interview/{interview_id}/report")
def get_report(interview_id: str, db: Session = Depends(get_db),
               token: str | None = Header(default=None, alias="X-Interview-Token")) -> dict:
    if not has_access(db, "interview", interview_id, token):
        raise HTTPException(status_code=403, detail="面试访问凭据无效")
    interview = get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="面试不存在")
    trees, bank = load_assets(settings)
    tree = trees.get(interview.position)
    report = build_report(db, interview, tree)
    report["practice_themes"] = weak_practice_themes(report, tree, bank, settings.max_plan_themes)
    return report


@router.post("/interview/{interview_id}/practice", response_model=InterviewCreateResponse)
def create_weak_practice(interview_id: str, db: Session = Depends(get_db),
                         token: str | None = Header(default=None, alias="X-Interview-Token")):
    if not has_access(db, "interview", interview_id, token):
        raise HTTPException(403, detail="面试访问凭据无效")
    interview = get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(404, detail="面试不存在")
    if interview.status != "finished":
        raise HTTPException(409, detail="请完成本场面试后再复练薄弱主题")
    trees, bank = load_assets(settings)
    tree = trees.get(interview.position)
    report = build_report(db, interview, tree)
    themes = weak_practice_themes(report, tree, bank, settings.max_plan_themes)
    if not themes:
        raise HTTPException(422, detail="当前报告没有可复练的薄弱知识主题，可在首页选择专项练习")
    plan = practice_plan(tree, bank, interview.position, interview.difficulty,
                         themes, settings.max_plan_themes)
    # 新场拥有独立凭据；不复制来源简历、回答、评分或用户关联。
    owner = db.get(ResourceOwner, ("interview", interview_id))
    return _save_interview(db, interview.position, interview.difficulty, plan,
                           account_id=owner.account_id if owner else None)


@router.get("/interview/{interview_id}")
def interview_summary(interview_id: str, db: Session = Depends(get_db),
                      token: str | None = Header(default=None, alias="X-Interview-Token")):
    """仅查询当前凭据对应面试的摘要，不枚举他人记录或触发模型。"""
    if not has_access(db, "interview", interview_id, token):
        raise HTTPException(403, detail="面试访问凭据无效")
    interview = get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(404, detail="面试不存在")
    data = summaries(db, [interview], settings.skill_tree_dir)[0]
    return Response(json.dumps(data, ensure_ascii=False), media_type="application/json",
                    headers={"Cache-Control": "no-store"})


@router.get("/interview/{interview_id}/report/export")
def export_report(interview_id: str, format: Literal["markdown", "json"] = "markdown",
                  db: Session = Depends(get_db),
                  token: str | None = Header(default=None, alias="X-Interview-Token")):
    from app.services.report_export import render_markdown
    report = get_report(interview_id, db, token)
    if format == "json":
        body, extension, media = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), "json", "application/json"
    else:
        body, extension, media = render_markdown(report), "md", "text/markdown"
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="interview-{report["interview_id"]}.{extension}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/positions")
def list_positions() -> dict:
    trees, bank = load_assets(settings)
    return {
        "positions": [
            {"id": pos, "display_name": t.display_name, "roots": t.root_names(),
             "practice_themes": available_themes(t, bank, pos),
             "practice_theme_limit": min(12, settings.max_plan_themes),
             "question_count": sum(q.position == pos for q in bank.questions)}
            for pos, t in trees.items()
            if any(q.position == pos and not q.is_coding and q.theme in t.root_names() for q in bank.questions)
        ]
    }


@router.get('/catalog')
def catalog(position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
            theme: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
            difficulty: Literal['easy', 'mid', 'hard'] | None = None,
            kind: Literal['all', 'knowledge', 'coding'] = 'all',
            q: Annotated[str | None, Query(max_length=100)] = None,
            offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
            limit: Annotated[int, Query(ge=1, le=24)] = 6):
    trees, bank = load_assets(settings)
    result = question_catalog(trees, bank, position=position, theme=theme, difficulty=difficulty,
        kind=kind, query=q, offset=offset, limit=limit, theme_limit=settings.max_plan_themes)
    return Response(json.dumps(result, ensure_ascii=False), media_type='application/json',
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/catalog/coverage')
def coverage(position: Annotated[str | None, Query(min_length=1, max_length=64)] = None):
    trees, bank = load_assets(settings)
    registry, state = load_registry(settings.question_bank_dir / 'source_registry.json')
    result = catalog_coverage(trees, bank, registry, state, position)
    return Response(json.dumps(result, ensure_ascii=False), media_type='application/json',
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get("/interview/{interview_id}/usage")
def interview_usage(interview_id: str, db: Session = Depends(get_db),
                    token: str | None = Header(default=None, alias="X-Interview-Token")):
    if not has_access(db, "interview", interview_id, token):
        raise HTTPException(403, detail="面试访问凭据无效")
    return usage_snapshot(db, "interview", interview_id)


@router.get("/resume/{resume_id}/usage")
def resume_usage(resume_id: str, db: Session = Depends(get_db),
                 token: str | None = Header(default=None, alias="X-Resume-Token")):
    if not has_access(db, "resume", resume_id, token):
        raise HTTPException(403, detail="简历访问凭据无效")
    return usage_snapshot(db, "resume", resume_id)
