"""Validation, public projection and feed queries for the community."""
from datetime import timedelta
import unicodedata

from fastapi import HTTPException
from sqlalchemy import case, delete, exists, func, or_, select, update
from sqlalchemy.orm import defer

from app.config import get_settings
from app.models.entities import Account, AccountProfile
from app.models.forum import (ForumBookmark, ForumComment, ForumIdentityChange, ForumLike, ForumPost,
                             ForumProfile, ForumReport)
from app.services.accounts import now_utc
from app.services.admin import stamp

IDENTITIES = {'student': '学生', 'employee': '公司职员'}
REASONS = {'spam': '广告', 'abuse': '辱骂', 'sexual': '色情', 'politics': '政治敏感',
           'copyright': '侵权', 'other': '其他'}


def clean(value, *, optional=False):
    value = value.strip()
    if not value and not optional:
        raise HTTPException(422, '请填写需要发布的内容。')
    if any(unicodedata.category(char) in {'Cc', 'Cs', 'Cf'} and char not in '\n\r\t\u200d' for char in value):
        raise HTTPException(422, '内容含有不可见控制字符，请检查后重试。')
    normalized = unicodedata.normalize('NFKC', value).casefold()
    folded = ''.join(char for char in normalized if char.isalnum())
    for term in get_settings().forum_blocked_terms:
        marker = ''.join(char for char in unicodedata.normalize('NFKC', term).casefold() if char.isalnum())
        if marker and marker in folded:
            raise HTTPException(422, '内容未通过社区发布检查，请修改后重试。')
    if normalized.count('http://') + normalized.count('https://') > 5:
        raise HTTPException(422, '链接过多，请保留与讨论直接相关的链接。')
    return value


def require_identity(db, account_id):
    row = db.get(ForumProfile, account_id)
    if row is None:
        raise HTTPException(409, '请先选择社区身份。')
    return row.identity


def public_post(db, post_id, *, lock=False):
    statement = select(ForumPost).where(ForumPost.id == post_id, ForumPost.status == 'published')
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise HTTPException(404, '帖子不存在或已下架。')
    return row


def person(account, profile):
    return {'id': account.id, 'username': account.username,
            'nickname': (profile.nickname if profile else '') or account.username,
            'avatar_url': '/api/forum/users/' + account.id + '/avatar' if profile and profile.avatar_version else None}


def page(statement, db, offset, limit):
    rows = db.execute(statement.offset(offset).limit(limit + 1)).all()
    return rows[:limit], offset + limit if len(rows) > limit else None


def post_feed(db, *, viewer=None, author=None, query='', mode='all', order='rank',
              offset=0, limit=20, post_id=None):
    threshold = get_settings().forum_featured_likes
    likes = select(func.count()).select_from(ForumLike).where(ForumLike.post_id == ForumPost.id).scalar_subquery()
    replies = select(func.count()).select_from(ForumComment).where(
        ForumComment.post_id == ForumPost.id, ForumComment.status == 'published').scalar_subquery()
    liked = exists().where(ForumLike.account_id == viewer, ForumLike.post_id == ForumPost.id)
    bookmarked = exists().where(ForumBookmark.account_id == viewer, ForumBookmark.post_id == ForumPost.id)
    statement = select(ForumPost, Account, AccountProfile, likes, replies, liked, bookmarked).join(
        Account, Account.id == ForumPost.author_id).outerjoin(AccountProfile, AccountProfile.account_id == Account.id
    ).options(defer(AccountProfile.avatar), defer(AccountProfile.email), defer(Account.password_hash)
    ).where(ForumPost.status == 'published')
    if not post_id:
        statement = statement.options(defer(ForumPost.body)).add_columns(func.substr(ForumPost.body, 1, 160))
    if post_id:
        statement = statement.where(ForumPost.id == post_id)
    if author:
        statement = statement.where(ForumPost.author_id == author)
    if mode == 'featured':
        statement = statement.where(likes >= threshold)
    if mode == 'saved':
        statement = statement.where(bookmarked)
    if query:
        identities = [key for key, label in IDENTITIES.items() if query.casefold() in label.casefold()
                      or query.casefold() in key]
        statement = statement.where(or_(ForumPost.title.icontains(query, autoescape=True),
            Account.username.icontains(query, autoescape=True), AccountProfile.nickname.icontains(query, autoescape=True),
            ForumPost.identity.in_(identities)))
    if order == 'rank':
        now = now_utc()
        recency = case((ForumPost.created_at >= now - timedelta(days=1), 12),
                       (ForumPost.created_at >= now - timedelta(days=7), 5), else_=0)
        statement = statement.order_by((3 * likes + 2 * replies + case((likes >= threshold, 8), else_=0) + recency).desc())
    statement = statement.order_by(ForumPost.created_at.desc(), ForumPost.id.desc())
    rows, next_offset = page(statement, db, offset, limit)
    items = []
    for row in rows:
        post, account, profile, n_likes, n_replies, is_liked, is_saved = row[:7]
        item = {'id': post.id, 'title': post.title, 'author': person(account, profile),
                'identity': post.identity, 'created_at': stamp(post.created_at), 'likes': n_likes,
                'comments': n_replies, 'featured': n_likes >= threshold, 'liked': is_liked, 'saved': is_saved}
        item.update(body=post.body) if post_id else item.update(excerpt=row[7])
        items.append(item)
    return {'items': items, 'next_offset': next_offset}


def public_users(db, query, offset, limit):
    identities = [key for key, label in IDENTITIES.items() if query.casefold() in label.casefold()
                  or query.casefold() in key]
    statement = select(Account, AccountProfile, ForumProfile.identity).join(
        ForumProfile, ForumProfile.account_id == Account.id
    ).outerjoin(AccountProfile, AccountProfile.account_id == Account.id
    ).options(defer(AccountProfile.avatar), defer(AccountProfile.email), defer(Account.password_hash)
    ).where(or_(Account.username.icontains(query, autoescape=True),
                AccountProfile.nickname.icontains(query, autoescape=True), ForumProfile.identity.in_(identities))
    ).order_by(Account.username, Account.id)
    rows, next_offset = page(statement, db, offset, limit)
    return {'items': [{**person(account, profile), 'identity': identity} for account, profile, identity in rows],
            'next_offset': next_offset}


def purge_account(db, account_id):
    """Existing account deletion also removes community content and references."""
    posts = select(ForumPost.id).where(ForumPost.author_id == account_id)
    comments = select(ForumComment.id).where(or_(ForumComment.author_id == account_id, ForumComment.post_id.in_(posts)))
    db.execute(delete(ForumReport).where(or_(ForumReport.reporter_id == account_id,
        ForumReport.post_id.in_(posts), ForumReport.comment_id.in_(comments))))
    db.execute(update(ForumReport).where(ForumReport.reviewer_id == account_id).values(reviewer_id=None))
    for model in (ForumLike, ForumBookmark):
        db.execute(delete(model).where(or_(model.account_id == account_id, model.post_id.in_(posts))))
    db.execute(delete(ForumComment).where(or_(ForumComment.author_id == account_id, ForumComment.post_id.in_(posts))))
    db.execute(delete(ForumPost).where(ForumPost.author_id == account_id))
    for model in (ForumIdentityChange, ForumProfile):
        db.execute(delete(model).where(model.account_id == account_id))
