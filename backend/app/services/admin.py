"""Read-only operations summaries. Never serialize private answers or credentials."""
from collections import Counter
from datetime import datetime, time, timedelta, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import case, func, or_, select

from app.config import get_settings
from app.models.entities import Account, AccountProfile, AccountSession, Interview, QuestionScore, ResourceOwner
from app.practice_policy import role_metadata
from app.services.accounts import now_utc, require_account

BEIJING = timezone(timedelta(hours=8))
STATUSES = ('created', 'running', 'finished', 'cancelled')


def is_admin(account_id):
    return account_id in {value.strip() for value in get_settings().admin_account_ids.split(',') if value.strip()}


def can_access_admin(account_id):
    return is_admin(account_id) or account_id in set(get_settings().admin_viewer_account_ids.split(','))


def capabilities(account_id):
    full = is_admin(account_id)
    return {'role': 'administrator' if full else 'viewer', 'permissions': {'export': full, 'review': full, 'audit': full}}


def require_admin(account: Account = Depends(require_account)):
    if not can_access_admin(account.id):
        raise HTTPException(403, '此账户没有管理工作台访问权限，请联系项目管理员。')
    return account


def stamp(value, *, local=False):
    if value is None:
        return None
    aware = value.astimezone() if local and value.tzinfo is None else value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def page_offset(total, offset, limit):
    return min(offset, ((total - 1) // limit) * limit) if total else 0


def daily_counts(db, column, days, *, completed=False):
    boundaries = [datetime.combine(day, time.min, tzinfo=BEIJING).astimezone().replace(tzinfo=None)
                  for day in days + [days[-1] + timedelta(days=1)]]
    statement = select(*[func.coalesce(func.sum(case(((column >= start) & (column < end), 1), else_=0)), 0)
                         for start, end in zip(boundaries, boundaries[1:])]).select_from(Interview)
    statement = statement.where(column >= boundaries[0], column < boundaries[-1])
    if completed:
        statement = statement.where(Interview.status == 'finished')
    return list(db.execute(statement).one())


def overview(db, bank, days_count):
    today = datetime.now(BEIJING).date()
    days = [today - timedelta(days=days_count - 1 - index) for index in range(days_count)]
    started = daily_counts(db, Interview.started_at, days)
    completed = daily_counts(db, Interview.ended_at, days, completed=True)
    statuses = dict(db.execute(select(Interview.status, func.count()).group_by(Interview.status)).all())
    total = sum(statuses.values())
    users = db.scalar(select(func.count()).select_from(Account))
    since = datetime.combine(days[0], time.min, tzinfo=BEIJING).astimezone(timezone.utc).replace(tzinfo=None)
    until = datetime.combine(today + timedelta(days=1), time.min, tzinfo=BEIJING).astimezone(timezone.utc).replace(tzinfo=None)
    new_users = db.scalar(select(func.count()).select_from(Account).where(Account.created_at >= since, Account.created_at < until))
    count, average = db.execute(select(func.count(), func.avg(QuestionScore.score)).select_from(QuestionScore)).one()
    roles = role_metadata()
    coverage = Counter(row.position for row in bank.questions)
    return {
        'generated_at': stamp(now_utc()), 'days': days_count, 'timezone': 'Asia/Shanghai',
        'metrics': {'interviews': total, 'finished': statuses.get('finished', 0), 'accounts': users,
                    'new_accounts': new_users, 'questions': len(bank.questions), 'positions': len(coverage),
                    'completion_rate': round(statuses.get('finished', 0) * 100 / total, 1) if total else 0,
                    'scored_answers': count, 'answer_average': round(average, 1) if average is not None else None},
        'trend': [{'date': day.isoformat(), 'started': int(started[index]), 'completed': int(completed[index])}
                  for index, day in enumerate(days)],
        'statuses': [{'key': key, 'count': value} for key, value in sorted(statuses.items())],
        'coverage': [{'position': key, 'name': roles.get(key, {}).get('name', key), 'count': value}
                     for key, value in sorted(coverage.items())],
        'roles': [{'id': key, 'name': value['name']} for key, value in roles.items()],
    }


def date_filter(statement, column, start, end, *, local=False):
    if end and end.year == 9999:
        raise HTTPException(422, '结束日期超出支持范围，请选择9999年以前的日期。')
    if start and end and start > end:
        raise HTTPException(422, '开始日期不能晚于结束日期。')
    def boundary(day):
        value = datetime.combine(day, time.min, tzinfo=BEIJING)
        return (value.astimezone() if local else value.astimezone(timezone.utc)).replace(tzinfo=None)
    if start:
        statement = statement.where(column >= boundary(start))
    if end:
        statement = statement.where(column < boundary(end + timedelta(days=1)))
    return statement


def interviews(db, *, query, position, status, offset, limit, start=None, end=None, sort='newest'):
    ownership = (ResourceOwner.resource_kind == 'interview') & (ResourceOwner.resource_id == Interview.id)
    statement = select(Interview.id, Interview.position, Interview.status, Interview.difficulty,
                       Interview.started_at, Interview.ended_at, Account.username).select_from(Interview).outerjoin(
                           ResourceOwner, ownership).outerjoin(Account, Account.id == ResourceOwner.account_id)
    if query:
        statement = statement.where(or_(Interview.id.contains(query, autoescape=True), Account.username.contains(query, autoescape=True)))
    if position:
        statement = statement.where(Interview.position == position)
    if status:
        statement = statement.where(Interview.status == status)
    statement = date_filter(statement, Interview.started_at, start, end, local=True)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    offset = page_offset(total, offset, limit)
    ordering = Interview.started_at.asc().nulls_last() if sort == 'oldest' else Interview.started_at.desc().nulls_last()
    rows = db.execute(statement.order_by(ordering, Interview.id).offset(offset).limit(limit)).all()
    ids = [row.id for row in rows]
    counts = dict(db.execute(select(QuestionScore.interview_id, func.count()).where(
        QuestionScore.interview_id.in_(ids)).group_by(QuestionScore.interview_id)).all()) if ids else {}
    items = [{'id': row.id, 'position': row.position, 'status': row.status, 'difficulty': row.difficulty,
              'started_at': stamp(row.started_at, local=True), 'ended_at': stamp(row.ended_at, local=True),
              'username': row.username or '匿名练习', 'scored_answers': counts.get(row.id, 0)} for row in rows]
    return {'items': items, 'total': total, 'offset': offset, 'limit': limit}


def accounts(db, *, query, bound, offset, limit, start=None, end=None, sort='newest'):
    statement = select(Account.id, Account.username, Account.created_at, AccountProfile.nickname,
                       AccountProfile.email.is_not(None).label('email_bound')).outerjoin(AccountProfile, AccountProfile.account_id == Account.id)
    if query:
        statement = statement.where(or_(Account.username.contains(query, autoescape=True), AccountProfile.nickname.contains(query, autoescape=True)))
    if bound:
        statement = statement.where(AccountProfile.email.is_not(None) if bound == 'bound' else AccountProfile.email.is_(None))
    statement = date_filter(statement, Account.created_at, start, end)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    offset = page_offset(total, offset, limit)
    ordering = Account.username.asc() if sort == 'name' else Account.created_at.asc() if sort == 'oldest' else Account.created_at.desc()
    rows = db.execute(statement.order_by(ordering, Account.id).offset(offset).limit(limit)).all()
    ids = [row.id for row in rows]
    sessions = dict(db.execute(select(AccountSession.account_id, func.count()).where(AccountSession.account_id.in_(ids),
        AccountSession.expires_at > now_utc()).group_by(AccountSession.account_id)).all()) if ids else {}
    practice = dict(db.execute(select(ResourceOwner.account_id, func.count()).where(ResourceOwner.account_id.in_(ids),
        ResourceOwner.resource_kind == 'interview').group_by(ResourceOwner.account_id)).all()) if ids else {}
    return {'items': [{'id': row.id, 'username': row.username, 'nickname': row.nickname or '',
                       'created_at': stamp(row.created_at), 'email_bound': row.email_bound,
                       'active_sessions': sessions.get(row.id, 0), 'interviews': practice.get(row.id, 0),
                       'is_admin': is_admin(row.id)} for row in rows], 'total': total, 'offset': offset, 'limit': limit}


def questions(bank, *, query, position, difficulty, kind, offset, limit):
    rows = [row for row in bank.questions if (not position or row.position == position)
            and (not difficulty or row.difficulty == difficulty)
            and (not kind or row.is_coding == (kind == 'coding'))
            and (not query or query.casefold() in '\n'.join([row.id, row.content, row.theme, row.source]).casefold())]
    rows.sort(key=lambda row: (row.position, row.theme, row.id))
    offset = page_offset(len(rows), offset, limit)
    return {'items': [{'id': row.id, 'position': row.position, 'theme': row.theme, 'difficulty': row.difficulty,
                       'content': row.content, 'source': row.source, 'is_coding': row.is_coding} for row in rows[offset:offset + limit]],
            'total': len(rows), 'offset': offset, 'limit': limit}
