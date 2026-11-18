"""Same-origin community API. Public reads and authenticated, bounded writes."""
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, defer

from app.config import get_settings
from app.db import get_db
from app.models.entities import Account, AccountProfile
from app.models.forum import (ForumBookmark, ForumComment, ForumIdentityChange, ForumLike, ForumPost,
                             ForumProfile, ForumReport)
from app.security import sanitize_pii
from app.services import forum
from app.services.accounts import lock_account, now_utc, optional_account, require_account
from app.services.admin import is_admin, stamp

router = APIRouter(prefix='/api/forum', tags=['forum'])
Id = Annotated[str, Path(pattern='^[0-9a-f]{32}$')]
Offset = Annotated[int, Query(ge=0, le=10000)]
Limit = Annotated[int, Query(ge=1, le=30)]
Sort = Literal['rank', 'latest']
Actor = Annotated[Account, Depends(require_account)]
DB = Annotated[Session, Depends(get_db)]


def forum_visitor(db: DB, authorization: Annotated[str | None, Header()] = None):
    """Public reads remain available when a browser holds a revoked session."""
    try:
        return optional_account(db, authorization)
    except HTTPException as error:
        if error.status_code != 401:
            raise
        return None


Visitor = Annotated[Account | None, Depends(forum_visitor)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IdentityInput(Input):
    identity: Literal['student', 'employee']


class PostInput(Input):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=8000)


class CommentInput(Input):
    body: str = Field(min_length=1, max_length=1500)


class ReportInput(Input):
    reason: Literal['spam', 'abuse', 'sexual', 'politics', 'copyright', 'other']
    note: str = Field(default='', max_length=300)


class ReviewInput(Input):
    decision: Literal['dismiss', 'hide']
    note: str = Field(min_length=1, max_length=300)


def account_id(viewer):
    return viewer.id if viewer else None


def public_profile(db, user_id):
    row = db.execute(select(Account, AccountProfile, ForumProfile).join(
        ForumProfile, ForumProfile.account_id == Account.id
    ).outerjoin(AccountProfile, AccountProfile.account_id == Account.id
    ).options(defer(AccountProfile.avatar), defer(AccountProfile.email), defer(Account.password_hash)
    ).where(Account.id == user_id)).one_or_none()
    if row is None:
        raise HTTPException(404, '该用户尚未开通社区主页。')
    return row


@router.get('/context')
def context(db: DB, viewer: Visitor):
    identity = db.get(ForumProfile, viewer.id) if viewer else None
    return {'identities': forum.IDENTITIES, 'report_reasons': forum.REASONS,
            'featured_likes': get_settings().forum_featured_likes,
            'viewer': {'id': viewer.id, 'identity': identity.identity if identity else None,
                       'can_moderate': is_admin(viewer.id)} if viewer else None}


@router.put('/identity')
def set_identity(payload: IdentityInput, db: DB, actor: Actor):
    lock_account(db, actor.id)
    row = db.get(ForumProfile, actor.id)
    if row is None or row.identity != payload.identity:
        now = now_utc()
        if row is None:
            row = ForumProfile(account_id=actor.id, identity=payload.identity, updated_at=now)
            db.add(row)
        else:
            row.identity, row.updated_at = payload.identity, now
        db.add(ForumIdentityChange(account_id=actor.id, identity=payload.identity, created_at=now))
    db.commit()
    return {'identity': row.identity, 'updated_at': stamp(row.updated_at)}


@router.get('/posts')
def posts(db: DB, viewer: Visitor, sort: Sort = 'rank',
          filter: Literal['all', 'featured', 'mine', 'saved'] = 'all',
          offset: Offset = 0, limit: Limit = 20):
    user = account_id(viewer)
    if filter in ('mine', 'saved') and not user:
        raise HTTPException(401, '请登录后查看个人帖子或收藏。')
    return forum.post_feed(db, viewer=user, author=user if filter == 'mine' else None,
                           mode=filter, order=sort, offset=offset, limit=limit)


@router.post('/posts', status_code=201)
def publish(payload: PostInput, db: DB, actor: Actor):
    title, body = forum.clean(payload.title), forum.clean(payload.body)
    if '\n' in title or '\r' in title:
        raise HTTPException(422, '标题请填写为一行。')
    lock_account(db, actor.id)
    post = ForumPost(author_id=actor.id, identity=forum.require_identity(db, actor.id), title=title, body=body)
    db.add(post)
    db.commit()
    return {'id': post.id}


@router.get('/posts/{post_id}')
def post_detail(post_id: Id, db: DB, viewer: Visitor):
    rows = forum.post_feed(db, viewer=account_id(viewer), post_id=post_id, order='latest', limit=1)['items']
    if not rows:
        raise HTTPException(404, '帖子不存在或已下架。')
    return rows[0]


@router.get('/posts/{post_id}/comments')
def replies(post_id: Id, db: DB, offset: Offset = 0, limit: Limit = 20):
    forum.public_post(db, post_id)
    statement = select(ForumComment, Account, AccountProfile).join(
        Account, Account.id == ForumComment.author_id
    ).outerjoin(AccountProfile, AccountProfile.account_id == Account.id
    ).options(defer(AccountProfile.avatar), defer(AccountProfile.email), defer(Account.password_hash)
    ).where(ForumComment.post_id == post_id, ForumComment.status == 'published'
    ).order_by(ForumComment.created_at, ForumComment.id)
    rows, next_offset = forum.page(statement, db, offset, limit)
    return {'items': [{'id': comment.id, 'body': comment.body, 'identity': comment.identity,
                       'created_at': stamp(comment.created_at), 'author': forum.person(account, profile)}
                      for comment, account, profile in rows], 'next_offset': next_offset}


@router.post('/posts/{post_id}/comments', status_code=201)
def reply(post_id: Id, payload: CommentInput, db: DB, actor: Actor):
    body = forum.clean(payload.body)
    lock_account(db, actor.id)
    forum.public_post(db, post_id, lock=True)
    row = ForumComment(post_id=post_id, author_id=actor.id, identity=forum.require_identity(db, actor.id), body=body)
    db.add(row)
    db.commit()
    return {'id': row.id}


def reaction(db, actor, post_id, model, enabled):
    lock_account(db, actor.id)
    forum.public_post(db, post_id, lock=True)
    key = (actor.id, post_id)
    row = db.get(model, key)
    if enabled and row is None:
        db.add(model(account_id=actor.id, post_id=post_id))
    elif not enabled and row is not None:
        db.delete(row)
    db.flush()
    likes = db.scalar(select(func.count()).select_from(ForumLike).where(ForumLike.post_id == post_id))
    result = {'liked': db.get(ForumLike, key) is not None, 'saved': db.get(ForumBookmark, key) is not None,
              'likes': likes, 'featured': likes >= get_settings().forum_featured_likes}
    db.commit()
    return result


@router.put('/posts/{post_id}/like')
def like(post_id: Id, db: DB, actor: Actor):
    return reaction(db, actor, post_id, ForumLike, True)


@router.delete('/posts/{post_id}/like')
def unlike(post_id: Id, db: DB, actor: Actor):
    return reaction(db, actor, post_id, ForumLike, False)


@router.put('/posts/{post_id}/bookmark')
def bookmark(post_id: Id, db: DB, actor: Actor):
    return reaction(db, actor, post_id, ForumBookmark, True)


@router.delete('/posts/{post_id}/bookmark')
def unbookmark(post_id: Id, db: DB, actor: Actor):
    return reaction(db, actor, post_id, ForumBookmark, False)


def report(db, actor, post_id, payload, comment_id=None):
    lock_account(db, actor.id)
    forum.public_post(db, post_id, lock=True)
    if comment_id:
        comment = db.get(ForumComment, comment_id)
        if comment is None or comment.post_id != post_id or comment.status != 'published':
            raise HTTPException(404, '该回复不存在或已下架。')
    target_kind, target_id = ('comment', comment_id) if comment_id else ('post', post_id)
    existing = db.scalar(select(ForumReport).where(ForumReport.reporter_id == actor.id,
                          ForumReport.target_kind == target_kind, ForumReport.target_id == target_id))
    if existing:
        return {'id': existing.id, 'status': existing.status, 'duplicate': True}
    recent = db.scalar(select(func.count()).select_from(ForumReport).where(
        ForumReport.reporter_id == actor.id, ForumReport.created_at >= now_utc() - timedelta(days=1)))
    if recent >= 5:
        raise HTTPException(429, '过去24小时已提交5次举报，请稍后再试。')
    row = ForumReport(reporter_id=actor.id, post_id=post_id, comment_id=comment_id,
                      target_kind=target_kind, target_id=target_id, reason=payload.reason,
                      note=sanitize_pii(payload.note.strip()))
    db.add(row)
    db.commit()
    return {'id': row.id, 'status': row.status, 'duplicate': False}


@router.post('/posts/{post_id}/reports')
def report_post(post_id: Id, payload: ReportInput, db: DB, actor: Actor):
    return report(db, actor, post_id, payload)


@router.post('/posts/{post_id}/comments/{comment_id}/reports')
def report_comment(post_id: Id, comment_id: Id, payload: ReportInput, db: DB, actor: Actor):
    return report(db, actor, post_id, payload, comment_id)


@router.get('/search')
def search(db: DB, viewer: Visitor, q: Annotated[str, Query(min_length=1, max_length=64)],
           post_offset: Offset = 0, user_offset: Offset = 0, limit: Limit = 12):
    query = q.strip()
    if not query:
        raise HTTPException(422, '请输入搜索关键词。')
    return {'query': query, 'posts': forum.post_feed(db, viewer=account_id(viewer), query=query,
            order='latest', offset=post_offset, limit=limit), 'users': forum.public_users(db, query, user_offset, limit)}


@router.get('/users/{user_id}')
def profile(user_id: Id, db: DB, viewer: Visitor):
    account, profile_row, membership = public_profile(db, user_id)
    post_count = db.scalar(select(func.count()).select_from(ForumPost).where(
        ForumPost.author_id == user_id, ForumPost.status == 'published'))
    saved_count = db.scalar(select(func.count()).select_from(ForumBookmark).join(ForumPost).where(
        ForumBookmark.account_id == user_id, ForumPost.status == 'published'))
    recent = forum.post_feed(db, viewer=account_id(viewer), author=user_id, order='latest', limit=3)['items']
    return {**forum.person(account, profile_row), 'identity': membership.identity,
            'post_count': post_count, 'saved_count': saved_count, 'recent_posts': recent,
            'is_self': account_id(viewer) == user_id}


@router.get('/users/{user_id}/posts')
def user_posts(user_id: Id, db: DB, viewer: Visitor, offset: Offset = 0, limit: Limit = 20):
    public_profile(db, user_id)
    return forum.post_feed(db, viewer=account_id(viewer), author=user_id, order='latest', offset=offset, limit=limit)


@router.get('/users/{user_id}/avatar', response_class=Response)
def avatar(user_id: Id, db: DB):
    data = db.scalar(select(AccountProfile.avatar).join(
        ForumProfile, ForumProfile.account_id == AccountProfile.account_id
    ).where(AccountProfile.account_id == user_id))
    if not data:
        raise HTTPException(404, '暂无头像。')
    return Response(data, media_type='image/png')


def reviewer(actor: Actor):
    if not is_admin(actor.id):
        raise HTTPException(403, '需要管理员权限才能审核举报。')
    return actor


@router.get('/moderation/reports')
def queue(db: DB, actor: Annotated[Account, Depends(reviewer)], offset: Offset = 0, limit: Limit = 20,
          status: Literal['pending', 'dismissed', 'actioned'] = 'pending'):
    statement = select(ForumReport, ForumPost.title, func.substr(ForumPost.body, 1, 500),
                       func.substr(ForumComment.body, 1, 500)).join(
        ForumPost, ForumPost.id == ForumReport.post_id
    ).outerjoin(ForumComment, ForumComment.id == ForumReport.comment_id
    ).where(ForumReport.status == status).order_by(ForumReport.created_at.desc(), ForumReport.id.desc())
    rows, next_offset = forum.page(statement, db, offset, limit)
    return {'items': [{'id': row.id, 'post_id': row.post_id, 'target_kind': row.target_kind, 'title': title,
                       'excerpt': reply if row.comment_id else excerpt, 'reason': row.reason, 'note': row.note,
                       'status': row.status, 'reviewer_id': row.reviewer_id, 'review_note': row.review_note,
                       'created_at': stamp(row.created_at), 'reviewed_at': stamp(row.reviewed_at)}
                      for row, title, excerpt, reply in rows], 'next_offset': next_offset}


@router.patch('/moderation/reports/{report_id}')
def review(report_id: Id, payload: ReviewInput, db: DB, actor: Annotated[Account, Depends(reviewer)]):
    note = sanitize_pii(payload.note.strip())
    if not note:
        raise HTTPException(422, '请填写审核说明。')
    status = 'actioned' if payload.decision == 'hide' else 'dismissed'
    changed = db.execute(update(ForumReport).where(ForumReport.id == report_id, ForumReport.status == 'pending')
                         .values(status=status, reviewed_at=now_utc(), reviewer_id=actor.id, review_note=note)).rowcount
    if not changed:
        raise HTTPException(409, '举报已处理或不存在，请刷新列表。')
    if payload.decision == 'hide':
        row = db.get(ForumReport, report_id)
        model, target = (ForumComment, row.comment_id) if row.comment_id else (ForumPost, row.post_id)
        db.execute(update(model).where(model.id == target).values(status='hidden'))
    db.commit()
    return {'id': report_id, 'status': status}


@router.get('/moderation/reports/{report_id}')
def report_target(report_id: Id, db: DB, actor: Annotated[Account, Depends(reviewer)]):
    row = db.get(ForumReport, report_id)
    if row is None:
        raise HTTPException(404, '举报记录不存在。')
    target = db.get(ForumComment, row.comment_id) if row.comment_id else db.get(ForumPost, row.post_id)
    if target is None:
        raise HTTPException(404, '被举报内容已删除。')
    return {'id': row.id, 'body': target.body, 'content_status': target.status}
