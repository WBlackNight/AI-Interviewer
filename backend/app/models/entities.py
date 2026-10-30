"""ORM 实体（SQLAlchemy 2.0 声明式）。

与 domain.py 的纯数据结构一一对应，转换集中在 repositories.py，
业务层不感知 ORM。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, LargeBinary, func, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), default="匿名用户")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    resumes: Mapped[list["Resume"]] = relationship(back_populates="user")


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured: Mapped[dict] = mapped_column(JSON, default=dict)  # ResumeData.as_dict()
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="resumes")


class Interview(Base):
    __tablename__ = "interview"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # 允许匿名面试（未上传简历时无关联用户）
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    resume_id: Mapped[str | None] = mapped_column(ForeignKey("resume.id"), nullable=True)
    position: Mapped[str] = mapped_column(String(64))
    difficulty: Mapped[str] = mapped_column(String(16), default="mid")
    plan: Mapped[list] = mapped_column(JSON, default=list)  # list[PlanItem dict]
    status: Mapped[str] = mapped_column(String(16), default="created")
    # created / running / finished / cancelled
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InterviewEvent(Base):
    """面试事件供恢复、回放与复盘；训练用途需要另行授权。"""

    __tablename__ = "interview_event"
    __table_args__ = (UniqueConstraint("interview_id", "seq", name="uq_interview_event_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[str] = mapped_column(
        ForeignKey("interview.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)  # 会话内单调递增
    type: Mapped[str] = mapped_column(String(32))  # EventType 常量
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Question(Base):
    __tablename__ = "question"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[str] = mapped_column(String(64), index=True)
    theme: Mapped[str] = mapped_column(String(64), index=True)
    difficulty: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    answer_points: Mapped[list] = mapped_column(JSON, default=list)
    is_coding: Mapped[bool] = mapped_column(default=False)
    testcases: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(64), default="builtin")


class QuestionScore(Base):
    __tablename__ = "question_score"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[str] = mapped_column(
        ForeignKey("interview.id"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(64))
    theme: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[str] = mapped_column(Text, default="")
    key_points_hit: Mapped[list] = mapped_column(JSON, default=list)
    key_points_missed: Mapped[list] = mapped_column(JSON, default=list)
    sandbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    probe_depth: Mapped[int] = mapped_column(Integer, default=0)
    answer_text: Mapped[str] = mapped_column(Text, default="")


class SkillNode(Base):
    __tablename__ = "skill_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("skill_node.id"), nullable=True
    )
    position: Mapped[str] = mapped_column(String(64), index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)


class UserSkillProfile(Base):
    """预留能力画像表；当前没有更新或消费链路。"""

    __tablename__ = "user_skill_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), index=True)
    skill_name: Mapped[str] = mapped_column(String(128), index=True)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class InterviewRuntime(Base):
    """新表支持旧数据库无损扩展；CAS 版本保护每轮原子提交。"""
    __tablename__ = "interview_runtime"
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    next_seq: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class InterviewSubmission(Base):
    __tablename__ = "interview_submission"
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview.id"), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    events: Mapped[list] = mapped_column(JSON)


class TurnMetadata(Base):
    __tablename__ = "turn_metadata"
    score_id: Mapped[int] = mapped_column(ForeignKey("question_score.id"), primary_key=True)
    turn_id: Mapped[str] = mapped_column(String(32), unique=True)
    main_question_id: Mapped[str] = mapped_column(String(64))
    skill_node_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScoreOriginRecord(Base):
    """评分时确定的来源和题目版本；旧评分无此行，不能用现配置回填。"""
    __tablename__ = "score_origin"
    score_id: Mapped[int] = mapped_column(ForeignKey("question_score.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class AccessGrant(Base):
    """匿名原型使用资源级 bearer token；只存散列。"""
    __tablename__ = "access_grant"
    resource_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))


class LLMBudgetUsage(Base):
    """独立计费账本，不随面试轮次回滚；pending在崩溃后保留供核对。"""
    __tablename__ = "llm_budget_usage"
    resource_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON)
    used_tokens: Mapped[int] = mapped_column(Integer, default=0)
    used_cost: Mapped[float] = mapped_column(Float, default=0)
    unknown_calls: Mapped[int] = mapped_column(Integer, default=0)
    pending: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class Account(Base):
    __tablename__ = "account"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AccountSession(Base):
    __tablename__ = "account_session"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class AccountProfile(Base):
    __tablename__ = 'account_profile'
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32), default='')
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, unique=True)
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AuthChallenge(Base):
    __tablename__ = 'auth_challenge'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    purpose: Mapped[str] = mapped_column(String(24), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey('account.id'), nullable=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    context: Mapped[str] = mapped_column(String(254), default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class ResourceOwner(Base):
    __tablename__ = "resource_owner"
    resource_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RevisionTask(Base):
    """用户主动保存的主题复习任务；不保存原回答或生成能力画像。"""
    __tablename__ = "revision_task"
    __table_args__ = (UniqueConstraint("account_id", "interview_id", "theme", name="uq_revision_task_source_theme"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), index=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview.id"), index=True)
    position: Mapped[str] = mapped_column(String(64))
    theme: Mapped[str] = mapped_column(String(64))
    source_score: Mapped[float] = mapped_column(Float)
    weak_score: Mapped[float] = mapped_column(Float)
    focus_points: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="todo")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RevisionPractice(Base):
    """任务到独立练习的关联；源任务删除时只清关联，不连带删除练习。"""
    __tablename__ = "revision_practice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("revision_task.id"), index=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview.id"), unique=True)


class RevisionSchedule(Base):
    """用户指定的日历日期；独立表兼容已有任务，删除源任务时一并清理。"""
    __tablename__ = "revision_schedule"
    task_id: Mapped[str] = mapped_column(ForeignKey("revision_task.id"), primary_key=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)


class RevisionNote(Base):
    """任务个人笔记；清空仍保留版本，避免旧页面覆盖后来的编辑。"""
    __tablename__ = "revision_note"
    task_id: Mapped[str] = mapped_column(ForeignKey("revision_task.id"), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionMark(Base):
    """账户题单只保存题目身份与手动状态，不复制题干、答案或评分。"""
    __tablename__ = "question_mark"
    __table_args__ = (UniqueConstraint("account_id", "position", "question_id", name="uq_question_mark_account_question"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), index=True)
    position: Mapped[str] = mapped_column(String(64))
    question_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="todo")
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PreparationPlan(Base):
    """用户主动设置的准备范围；目标日期不自动触发练习或改变评分。"""
    __tablename__ = "preparation_plan"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[str] = mapped_column(String(64))
    themes: Mapped[list] = mapped_column(JSON)
    difficulty: Mapped[str] = mapped_column(String(16))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class PreparationPractice(Base):
    """准备计划关联独立面试；移除计划只清关联，保留练习记录。"""
    __tablename__ = "preparation_practice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("preparation_plan.id"), index=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview.id"), unique=True)
