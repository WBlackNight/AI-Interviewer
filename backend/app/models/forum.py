"""Forum rows share the existing account identity and migration registry."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.entities import Base, _uuid
from app.services.accounts import now_utc


class ForumProfile(Base):
    __tablename__ = 'forum_profile'
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), primary_key=True)
    identity: Mapped[str] = mapped_column(String(24), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumIdentityChange(Base):
    __tablename__ = 'forum_identity_change'
    __table_args__ = (Index('ix_forum_identity_account_date', 'account_id', 'created_at'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'))
    identity: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumPost(Base):
    __tablename__ = 'forum_post'
    __table_args__ = (
        CheckConstraint("status IN ('published', 'hidden')", name='ck_forum_post_status'),
        Index('ix_forum_post_status_date', 'status', 'created_at', 'id'),
        Index('ix_forum_post_author_date', 'author_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    author_id: Mapped[str] = mapped_column(ForeignKey('account.id'))
    identity: Mapped[str] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default='published')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumComment(Base):
    __tablename__ = 'forum_comment'
    __table_args__ = (
        CheckConstraint("status IN ('published', 'hidden')", name='ck_forum_comment_status'),
        Index('ix_forum_comment_post_status_date', 'post_id', 'status', 'created_at', 'id'),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(ForeignKey('forum_post.id'))
    author_id: Mapped[str] = mapped_column(ForeignKey('account.id'), index=True)
    identity: Mapped[str] = mapped_column(String(24))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default='published')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumLike(Base):
    __tablename__ = 'forum_like'
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), primary_key=True)
    post_id: Mapped[str] = mapped_column(ForeignKey('forum_post.id'), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumBookmark(Base):
    __tablename__ = 'forum_bookmark'
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), primary_key=True)
    post_id: Mapped[str] = mapped_column(ForeignKey('forum_post.id'), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ForumReport(Base):
    __tablename__ = 'forum_report'
    __table_args__ = (
        UniqueConstraint('reporter_id', 'target_kind', 'target_id', name='uq_forum_report_once'),
        CheckConstraint("status IN ('pending', 'dismissed', 'actioned')", name='ck_forum_report_status'),
        Index('ix_forum_report_reporter_date', 'reporter_id', 'created_at'),
        Index('ix_forum_report_queue', 'status', 'created_at', 'id'),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('account.id'))
    post_id: Mapped[str] = mapped_column(ForeignKey('forum_post.id'), index=True)
    comment_id: Mapped[str | None] = mapped_column(ForeignKey('forum_comment.id'), index=True)
    target_kind: Mapped[str] = mapped_column(String(8))
    target_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(300), default='')
    status: Mapped[str] = mapped_column(String(16), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('account.id'), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str] = mapped_column(String(300), default='')
