"""Bounded exports and versioned review metadata, with atomic administrative audit."""
import csv
import hashlib
import io
import json
from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.models.entities import Account, AdminAudit, AdminQuestionReview
from app.security import sanitize_pii
from app.services import admin
from app.services.accounts import now_utc


def audit(db, actor_id, action, resource, request_id, *, outcome='succeeded', details=None):
    db.add(AdminAudit(actor_id=actor_id, action=action, resource=resource, request_id=request_id,
                      outcome=outcome, details=details or {}, created_at=now_utc()))


def fingerprint(question):
    fields = ('position', 'theme', 'difficulty', 'content', 'source', 'is_coding', 'answer_points', 'testcases')
    data = asdict(question)
    return hashlib.sha256(json.dumps({key: data[key] for key in fields},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def review_data(question, row):
    current = fingerprint(question)
    stale = bool(row and row.content_hash != current)
    return {'review_status': row.status if row and not stale else 'pending',
            'review_note': row.note if row else '', 'review_version': row.version if row else 0,
            'content_hash': current, 'review_stale': stale,
            'reviewed_at': admin.stamp(row.updated_at) if row else None}


def questions(db, bank, *, query='', position='', difficulty='', kind='', review='', sort='default', offset=0, limit=10):
    result = admin.questions(bank, query=query, position=position, difficulty=difficulty, kind=kind,
                             offset=0, limit=max(1, len(bank.questions)))
    originals = {row.id: row for row in bank.questions}
    saved = {row.question_id: row for row in db.scalars(select(AdminQuestionReview).where(
        AdminQuestionReview.question_id.in_(list(originals)))).all()}
    rows = [{**row, **review_data(originals[row['id']], saved.get(row['id']))} for row in result['items']]
    if review:
        rows = [row for row in rows if row['review_status'] == review]
    if sort == 'name':
        rows.sort(key=lambda row: (row['content'], row['id']))
    elif sort == 'difficulty':
        rows.sort(key=lambda row: ({'easy': 0, 'mid': 1, 'hard': 2}.get(row['difficulty'], 3), row['id']))
    offset = admin.page_offset(len(rows), offset, limit)
    return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit}


def save_review(db, bank, actor_id, question_id, payload, request_id):
    question = next((row for row in bank.questions if row.id == question_id), None)
    if question is None:
        raise HTTPException(404, '该题目已不在运行题库中，请重新读取。')
    current_hash = fingerprint(question)
    if current_hash != payload.content_hash:
        raise HTTPException(409, '题目内容已经更新，请重新读取后再审校。')
    existing = db.get(AdminQuestionReview, question_id)
    version = existing.version if existing else 0
    if version != payload.expected_version:
        raise HTTPException(409, '审校记录已被其他管理员更新，请重新读取后再保存。')
    previous = existing.status if existing and existing.content_hash == current_hash else 'pending'
    changes = dict(content_hash=current_hash, status=payload.status, note=sanitize_pii(payload.note.strip()),
                   version=version + 1, reviewer_id=actor_id, updated_at=now_utc())
    try:
        if existing is None:
            db.add(AdminQuestionReview(question_id=question_id, **changes))
        else:
            changed = db.execute(update(AdminQuestionReview).where(AdminQuestionReview.question_id == question_id,
                AdminQuestionReview.version == version).values(**changes)).rowcount
            if not changed:
                raise HTTPException(409, '审校记录已更新，请重新读取。')
        audit(db, actor_id, 'question_review', question_id, request_id,
              details={'from': previous, 'to': payload.status, 'version': version + 1})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '审校记录刚被创建，请重新读取后再保存。') from None
    return {'message': '审校记录已保存', 'version': version + 1}


def audit_list(db, *, query='', action='', outcome='', start=None, end=None, offset=0, limit=10):
    statement = select(AdminAudit, Account.username).outerjoin(Account, AdminAudit.actor_id == Account.id)
    if query:
        statement = statement.where(or_(AdminAudit.request_id.contains(query, autoescape=True),
            AdminAudit.resource.contains(query, autoescape=True), Account.username.contains(query, autoescape=True)))
    if action:
        statement = statement.where(AdminAudit.action == action)
    if outcome:
        statement = statement.where(AdminAudit.outcome == outcome)
    statement = admin.date_filter(statement, AdminAudit.created_at, start, end)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    offset = admin.page_offset(total, offset, limit)
    rows = db.execute(statement.order_by(AdminAudit.created_at.desc(), AdminAudit.id).offset(offset).limit(limit)).all()
    return {'items': [{'id': row.id, 'actor': username or '已注销账户', 'action': row.action,
                       'outcome': row.outcome, 'resource': row.resource, 'request_id': row.request_id,
                       'created_at': admin.stamp(row.created_at), 'details': row.details} for row, username in rows],
            'total': total, 'offset': offset, 'limit': limit}


def csv_cell(value):
    text = '' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        text = "'" + text
    return text


def export_csv(db, bank, resource, filters, actor_id, request_id):
    common = dict(query=filters['query'], offset=0, limit=1001)
    if resource == 'questions':
        result = questions(db, bank, **common, position=filters['position'], difficulty=filters['difficulty'],
                           kind=filters['kind'], review=filters['review'], sort=filters['sort'])
        fields = [('id', '题目编号'), ('position', '练习方向'), ('theme', '主题'), ('difficulty', '难度'),
                  ('content', '题目内容'), ('source', '来源'), ('review_status', '审校状态')]
    elif resource == 'interviews':
        result = admin.interviews(db, **common, position=filters['position'], status=filters['status'],
                                  start=filters['start'], end=filters['end'], sort=filters['sort'])
        fields = [('id', '场次编号'), ('position', '练习方向'), ('status', '状态'), ('username', '用户名'),
                  ('scored_answers', '已评分轮数'), ('started_at', '开始时间'), ('ended_at', '结束时间')]
    else:
        result = admin.accounts(db, **common, bound=filters['bound'], start=filters['start'], end=filters['end'], sort=filters['sort'])
        fields = [('username', '用户名'), ('nickname', '昵称'), ('created_at', '注册时间'),
                  ('email_bound', '是否绑定邮箱'), ('interviews', '练习数'), ('active_sessions', '有效会话数')]
    if result['total'] > 1000:
        raise HTTPException(422, '结果超过1000条，请缩小筛选范围后再导出。')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow([label for _, label in fields])
    for row in result['items']:
        writer.writerow([csv_cell(row.get(key)) for key, _ in fields])
    content = ('\ufeff' + stream.getvalue()).encode('utf-8')
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(422, '导出内容超过5MB，请缩小筛选范围。')
    audit(db, actor_id, 'data_export', resource, request_id, details={'rows': result['total']})
    db.commit()
    return content, result['total']
