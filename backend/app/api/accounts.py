"""账户与历史API；资源内容接口继续通过原资源token头授权。"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import select, delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.entities import (Account, AccountSession, AccessGrant, ResourceOwner,
    Interview, InterviewEvent, InterviewRuntime, InterviewSubmission, QuestionScore,
    TurnMetadata, Resume, User, UserSkillProfile, ScoreOriginRecord, RevisionTask, RevisionPractice, RevisionSchedule, RevisionNote, QuestionMark, PreparationPlan, PreparationPractice)
from app.security import has_access
from app.services.accounts import (AuthThrottle, DUMMY_HASH, attach_owner, bearer_token,
    hash_password, issue_session, lock_account, require_account, token_hash, verify_password)
from app.services.history import account_history
from app.services.review import account_review
from app.services.dashboard import account_dashboard
from app.services.revision import add_revision_tasks, list_revision_tasks, update_revision_task, start_revision_practice, update_revision_note, get_revision_note
from app.schemas import RevisionPracticeResponse
from app.services import account_security as security
from app.models.entities import AccountProfile, AuthChallenge

router = APIRouter(prefix="/api", tags=["accounts"])
throttle = AuthThrottle()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern="^[a-z0-9_]+$")
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: SecretStr = Field(min_length=64, max_length=64)


class Registration(Credentials):
    password_confirm: SecretStr = Field(min_length=12,max_length=128)
    captcha_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    captcha_code: str = Field(min_length=1,max_length=10)

    @model_validator(mode='after')
    def matching_passwords(self):
        if self.password.get_secret_value()!=self.password_confirm.get_secret_value():
            raise HTTPException(422,'两次输入的密码不一致')
        return self


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=12, max_length=128)


class RevisionTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["todo", "done"] | None = None
    due_date: date | None = None

    @field_validator("due_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("使用 YYYY-MM-DD 日期或 null")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not 2000 <= parsed.year <= 2100:
            raise ValueError("日期范围为 2000-01-01 至 2100-12-31")
        return parsed

    @model_validator(mode="after")
    def nonempty_update(self):
        if not self.model_fields_set or ("status" in self.model_fields_set and self.status is None):
            raise ValueError("至少提交有效状态或复习日期")
        return self


class RevisionNoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(strict=True, max_length=2000)
    expected_version: int = Field(strict=True, ge=0)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_newlines(cls, value):
        return value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else value


def auth_work(request: Request):
    # 不信任客户端X-Forwarded-For，反代部署另配可信代理和分布式配额。
    throttle.check(request.client.host if request.client else "unknown")
    if not throttle.work.acquire(blocking=False):
        raise HTTPException(429, "登录服务繁忙，请稍后再试")
    try:
        yield
    finally:
        throttle.work.release()


def session_response(db, account):
    lock_account(db, account.id)
    token, expires = issue_session(db, account.id)
    db.commit()
    return {"account": security.profile_data(db,account),
            "access_token": token, "expires_at": expires.isoformat() + "Z"}


@router.post("/auth/register", dependencies=[Depends(auth_work)])
def register(payload: Registration, db: Session = Depends(get_db)):
    security.consume(db,payload.captcha_id,payload.captcha_code,'register')
    account = Account(username=payload.username, password_hash=hash_password(payload.password.get_secret_value()))
    db.add(account)
    try:
        db.flush()
        return session_response(db, account)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该用户名已被注册，请更换用户名") from None


@router.post("/auth/login", dependencies=[Depends(auth_work)])
def login(payload: Credentials, db: Session = Depends(get_db)):
    account = db.scalar(select(Account).where(Account.username == payload.username))
    valid = verify_password(payload.password.get_secret_value(), account.password_hash if account else DUMMY_HASH)
    if not account or not valid:
        raise HTTPException(401, "用户名或密码错误")
    return session_response(db, account)


@router.get("/auth/me")
def me(db: Session = Depends(get_db),account: Account = Depends(require_account)):
    return security.profile_data(db,account)


@router.get('/auth/captcha',dependencies=[Depends(auth_work)])
def registration_captcha(db: Session = Depends(get_db)):
    return security.captcha(db)


@router.get('/auth/username-availability',dependencies=[Depends(auth_work)])
def username_available(username:Annotated[str,Query(min_length=3,max_length=32,pattern=r'^[A-Za-z0-9_]+$')],db:Session=Depends(get_db)):
    return {'available':db.scalar(select(Account.id).where(Account.username==username.lower())) is None}


@router.post("/auth/logout")
def logout(db: Session = Depends(get_db), account: Account = Depends(require_account),
           authorization: str | None = Header(default=None)):
    db.execute(delete(AccountSession).where(AccountSession.token_hash == token_hash(bearer_token(authorization))))
    db.commit()
    return {"logged_out": True}


@router.post("/account/interviews/{interview_id}/claim")
def claim(interview_id: str, payload: ClaimRequest, db: Session = Depends(get_db),
          account: Account = Depends(require_account)):
    owner = db.get(ResourceOwner, ("interview", interview_id))
    if owner:
        if owner.account_id == account.id:
            return {"claimed": True, "interview_id": interview_id}
        raise HTTPException(403, "无法认领该面试")
    if not has_access(db, "interview", interview_id, payload.access_token.get_secret_value()):
        raise HTTPException(403, "面试访问凭据无效")
    if db.get(Interview, interview_id) is None:
        raise HTTPException(404, "面试不存在")
    # 账户行更新锁防止与注销交错。资源复合主键防止双账户同时认领。
    lock_account(db, account.id)
    attach_owner(db, "interview", interview_id, account.id)
    db.execute(delete(AccessGrant).where(AccessGrant.resource_kind == "interview",
                                        AccessGrant.resource_id == interview_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        owner = db.get(ResourceOwner, ("interview", interview_id))
        if not owner or owner.account_id != account.id:
            raise HTTPException(409, "面试已被认领，请刷新") from None
    return {"claimed": True, "interview_id": interview_id}


@router.get("/account/interviews")
def history(db: Session = Depends(get_db), account: Account = Depends(require_account),
            status: Literal['created', 'running', 'finished', 'cancelled'] | None = None,
            position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
            difficulty: Literal['easy', 'mid', 'hard'] | None = None,
            offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
            limit: Annotated[int, Query(ge=1, le=50)] = 20):
    return account_history(db, account.id, get_settings().skill_tree_dir, offset=offset, limit=limit,
                           status=status, position=position, difficulty=difficulty)


@router.get("/account/review")
def review(db: Session = Depends(get_db), account: Account = Depends(require_account),
           position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
           theme: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
           offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
           limit: Annotated[int, Query(ge=1, le=50)] = 20):
    return account_review(db, account.id, get_settings().skill_tree_dir,
                          position=position, theme=theme, offset=offset, limit=limit)


@router.get('/account/dashboard')
def dashboard(db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return account_dashboard(db, account.id, get_settings().skill_tree_dir)


@router.post("/account/interviews/{interview_id}/revision-tasks")
def add_tasks(interview_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return add_revision_tasks(db, account.id, interview_id)


@router.get("/account/revision-tasks")
def tasks(db: Session = Depends(get_db), account: Account = Depends(require_account),
          status: Literal["todo", "done"] | None = None,
          due: Literal["all", "today", "overdue", "upcoming", "unscheduled"] = "all",
          q: Annotated[str | None, Query(max_length=100)] = None,
          note_filter: Literal["all", "with", "without"] = "all",
          position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
          offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
          limit: Annotated[int, Query(ge=1, le=50)] = 20):
    return list_revision_tasks(db, account.id, get_settings().skill_tree_dir,
        status=status, position=position, due=due, offset=offset, limit=limit, query=q, note_filter=note_filter)


@router.patch("/account/revision-tasks/{task_id}")
def update_task(task_id: str, payload: RevisionTaskUpdate, db: Session = Depends(get_db),
                account: Account = Depends(require_account)):
    return update_revision_task(db, account.id, task_id, **payload.model_dump(exclude_unset=True))


@router.post("/account/revision-tasks/{task_id}/practice", response_model=RevisionPracticeResponse)
def task_practice(task_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return start_revision_practice(db, account.id, task_id, get_settings())


@router.put("/account/revision-tasks/{task_id}/note")
def update_note(task_id: str, payload: RevisionNoteUpdate, db: Session = Depends(get_db),
                account: Account = Depends(require_account)):
    return update_revision_note(db, account.id, task_id, payload.content, payload.expected_version)


@router.get("/account/revision-tasks/{task_id}/note")
def read_note(task_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return get_revision_note(db, account.id, task_id)


def purge_interviews(db, ids):
    if not ids:
        return
    score_ids = select(QuestionScore.id).where(QuestionScore.interview_id.in_(ids))
    task_ids = select(RevisionTask.id).where(RevisionTask.interview_id.in_(ids))
    db.execute(delete(PreparationPractice).where(PreparationPractice.interview_id.in_(ids)))
    db.execute(delete(RevisionNote).where(RevisionNote.task_id.in_(task_ids)))
    db.execute(delete(RevisionSchedule).where(RevisionSchedule.task_id.in_(task_ids)))
    db.execute(delete(RevisionPractice).where(or_(RevisionPractice.interview_id.in_(ids), RevisionPractice.task_id.in_(task_ids))))
    db.execute(delete(RevisionTask).where(RevisionTask.interview_id.in_(ids)))
    db.execute(delete(ScoreOriginRecord).where(ScoreOriginRecord.score_id.in_(score_ids)))
    db.execute(delete(TurnMetadata).where(TurnMetadata.score_id.in_(score_ids)))
    for model in (QuestionScore, InterviewEvent, InterviewSubmission, InterviewRuntime):
        db.execute(delete(model).where(model.interview_id.in_(ids)))
    db.execute(delete(AccessGrant).where(AccessGrant.resource_kind == "interview", AccessGrant.resource_id.in_(ids)))
    db.execute(delete(ResourceOwner).where(ResourceOwner.resource_kind == "interview", ResourceOwner.resource_id.in_(ids)))
    db.execute(delete(Interview).where(Interview.id.in_(ids)))


@router.delete("/account/interviews/{interview_id}")
def delete_interview(interview_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    lock_account(db, account.id)
    owner = db.get(ResourceOwner, ("interview", interview_id))
    if not owner or owner.account_id != account.id:
        raise HTTPException(403, "无权删除该面试")
    row = db.get(Interview, interview_id)
    if row and row.status == "running":
        raise HTTPException(409, "请先完成或取消进行中的面试后再删除")
    purge_interviews(db, [interview_id])
    db.commit()
    return {"deleted": True}


@router.delete("/account", dependencies=[Depends(auth_work)])
def delete_account(payload: DeleteAccountRequest, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    if not verify_password(payload.password.get_secret_value(), account.password_hash):
        raise HTTPException(401, "密码错误")
    lock_account(db, account.id)
    ids = list(db.scalars(select(ResourceOwner.resource_id).where(
        ResourceOwner.account_id == account.id, ResourceOwner.resource_kind == "interview")))
    if db.scalar(select(Interview.id).where(Interview.id.in_(ids), Interview.status == "running").limit(1)):
        raise HTTPException(409, "请先完成或取消账户中进行的面试后再删除账户")
    resume_ids = list(db.scalars(select(ResourceOwner.resource_id).where(
        ResourceOwner.account_id == account.id, ResourceOwner.resource_kind == "resume")))
    if db.scalar(select(Interview.id).where(Interview.resume_id.in_(resume_ids), ~Interview.id.in_(ids)).limit(1)):
        raise HTTPException(409, "简历仍有其他记录引用，请先处理关联记录")
    user_ids = list(db.scalars(select(Resume.user_id).where(Resume.id.in_(resume_ids))))
    purge_interviews(db, ids)
    remaining_tasks = select(RevisionTask.id).where(RevisionTask.account_id == account.id)
    db.execute(delete(RevisionNote).where(RevisionNote.task_id.in_(remaining_tasks)))
    db.execute(delete(RevisionSchedule).where(RevisionSchedule.task_id.in_(remaining_tasks)))
    db.execute(delete(RevisionPractice).where(RevisionPractice.task_id.in_(remaining_tasks)))
    db.execute(delete(RevisionTask).where(RevisionTask.account_id == account.id))
    db.execute(delete(Resume).where(Resume.id.in_(resume_ids)))
    for user_id in set(user_ids):
        if not db.scalar(select(Resume.id).where(Resume.user_id == user_id).limit(1)) and not db.scalar(
                select(Interview.id).where(Interview.user_id == user_id).limit(1)):
            db.execute(delete(UserSkillProfile).where(UserSkillProfile.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
    db.execute(delete(AccessGrant).where(AccessGrant.resource_kind == "resume", AccessGrant.resource_id.in_(resume_ids)))
    db.execute(delete(ResourceOwner).where(ResourceOwner.account_id == account.id))
    db.execute(delete(AccountSession).where(AccountSession.account_id == account.id))
    db.execute(delete(AuthChallenge).where(AuthChallenge.account_id == account.id))
    db.execute(delete(AccountProfile).where(AccountProfile.account_id == account.id))
    db.execute(delete(QuestionMark).where(QuestionMark.account_id == account.id))
    plan_ids = select(PreparationPlan.id).where(PreparationPlan.account_id == account.id)
    db.execute(delete(PreparationPractice).where(PreparationPractice.plan_id.in_(plan_ids)))
    db.execute(delete(PreparationPlan).where(PreparationPlan.account_id == account.id))
    db.execute(delete(Account).where(Account.id == account.id))
    db.commit()
    return {"deleted": True}
