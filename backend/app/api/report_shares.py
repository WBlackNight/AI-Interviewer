"""Expiring report snapshots with separately revocable bearer links."""
import re
import secrets
import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.factories import load_assets
from app.models.entities import Account, Interview, ReportShare, ResourceOwner
from app.services.accounts import lock_account, now_utc, require_account, token_hash
from app.services.report import build_report

router = APIRouter(prefix="/api", tags=["report-shares"])


class ShareInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    hours: Literal[24, 72, 168] = 24
    scope: Literal["summary", "answers"] = "summary"


def owned_report(db, account_id, interview_id):
    owner = db.get(ResourceOwner, ("interview", interview_id))
    if not owner or owner.account_id != account_id:
        raise HTTPException(404, "报告不存在")
    row = db.get(Interview, interview_id)
    if not row or row.status != "finished":
        raise HTTPException(409, "完成面试后可以分享报告")
    return row


def summary(row):
    return {"id": row.id, "scope": row.scope, "created_at": row.created_at.isoformat() + "Z",
            "expires_at": row.expires_at.isoformat() + "Z", "revoked": row.revoked,
            "active": not row.revoked and row.expires_at > now_utc()}


@router.get("/account/interviews/{interview_id}/shares")
def list_shares(interview_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    owned_report(db, account.id, interview_id)
    rows = db.scalars(select(ReportShare).where(ReportShare.account_id == account.id,
        ReportShare.interview_id == interview_id).order_by(ReportShare.revoked.asc(),
        ReportShare.expires_at.desc()).limit(50))
    return {"items": [summary(row) for row in rows]}


@router.post("/account/interviews/{interview_id}/shares")
def create_share(interview_id: str, payload: ShareInput, db: Session = Depends(get_db),
                 account: Account = Depends(require_account)):
    lock_account(db, account.id)
    interview = owned_report(db, account.id, interview_id)
    count = db.scalar(select(func.count()).select_from(ReportShare).where(
        ReportShare.account_id == account.id, ReportShare.revoked.is_(False), ReportShare.expires_at > now_utc()))
    if count >= 20:
        raise HTTPException(409, "最多保留20个有效分享，请先撤销不需要的链接")
    trees, _ = load_assets(get_settings())
    report = build_report(db, interview, trees.get(interview.position))
    snapshot = {key: report[key] for key in ("position_display_name", "overall", "dimensions",
        "theme_avg", "recommendations", "question_count", "answer_count")}
    if payload.scope == "answers":
        snapshot["per_question"] = [{key: row[key] for key in ("content", "answer_text", "score",
            "key_points_hit", "key_points_missed")} for row in report["per_question"]]
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 2_000_000:
        raise HTTPException(413, "报告内容较多，请改为只分享评分摘要")
    secret = secrets.token_hex(32)
    moment = now_utc()
    row = ReportShare(account_id=account.id, interview_id=interview.id, token_hash=token_hash(secret),
        scope=payload.scope, snapshot=snapshot, created_at=moment,
        expires_at=moment + timedelta(hours=payload.hours), revoked=False)
    db.add(row)
    db.commit()
    return {**summary(row), "share_path": "/share#" + secret}


@router.post("/account/report-shares/{share_id}/revoke")
def revoke_share(share_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    lock_account(db, account.id)
    row = db.scalar(select(ReportShare).where(ReportShare.id == share_id, ReportShare.account_id == account.id))
    if not row:
        raise HTTPException(404, "分享不存在")
    row.revoked = True
    db.commit()
    return {"revoked": True}


@router.get("/shared-report")
def read_share(token: str = Header(default="", alias="X-Report-Share"), db: Session = Depends(get_db)):
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise HTTPException(404, "链接已失效或不可访问，请联系分享者")
    row = db.scalar(select(ReportShare).where(ReportShare.token_hash == token_hash(token),
        ReportShare.revoked.is_(False), ReportShare.expires_at > now_utc()))
    if not row:
        raise HTTPException(404, "链接已失效或不可访问，请联系分享者")
    owner = db.get(ResourceOwner, ("interview", row.interview_id))
    if not owner or owner.account_id != row.account_id:
        raise HTTPException(404, "链接已失效或不可访问，请联系分享者")
    return {"report": row.snapshot, "scope": row.scope, "expires_at": row.expires_at.isoformat() + "Z"}
