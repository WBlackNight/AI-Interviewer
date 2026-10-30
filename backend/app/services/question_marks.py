"""个人题单：账户内去重、版本保护，题目内容按当前运行资产解析。"""
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models.entities import QuestionMark
from app.services.accounts import lock_account, now_utc
from app.services.practice import available_themes

MAX_MARKS = 500


def serialize(row, questions, allowed):
    question = questions.get((row.position, row.question_id))
    return {'id': row.id, 'position': row.position, 'question_id': row.question_id,
            'status': row.status, 'version': row.version,
            'created_at': row.created_at.isoformat() + 'Z',
            'reviewed_at': row.reviewed_at.isoformat() + 'Z' if row.reviewed_at else None,
            'available': question is not None,
            'can_practice': bool(question and not question.is_coding and question.theme in allowed.get(row.position, set())),
            'question': {'theme': question.theme, 'difficulty': question.difficulty,
                         'content': question.content, 'source': question.source,
                         'is_coding': question.is_coding} if question else None}


def list_marks(db, account_id, trees, bank, *, position=None, status=None, query=None, offset=0, limit=8):
    rows = list(db.scalars(select(QuestionMark).where(QuestionMark.account_id == account_id)
                          .order_by(QuestionMark.created_at.desc(), QuestionMark.id.desc())))
    positions = [{'id': key, 'display_name': trees[key].display_name if key in trees else key}
                 for key in sorted({row.position for row in rows})]
    questions = {(q.position, q.id): q for q in bank.questions}
    allowed = {key: set(available_themes(tree, bank, key)) for key, tree in trees.items()}
    if position is not None:
        rows = [row for row in rows if row.position == position]
    query = (query or '').strip()
    if query:
        term = query.casefold()
        def matches(row):
            question = questions.get((row.position, row.question_id))
            values = [row.question_id]
            if question:
                values.extend([question.theme, question.content, question.source])
            return term in '\n'.join(values).casefold()
        rows = [row for row in rows if matches(row)]
    counts = {'all': len(rows), 'todo': sum(row.status == 'todo' for row in rows),
              'done': sum(row.status == 'done' for row in rows),
              'unavailable': sum((row.position, row.question_id) not in questions for row in rows)}
    if status is not None:
        rows = [row for row in rows if row.status == status]
    return {'items': [serialize(row, questions, allowed) for row in rows[offset:offset + limit]],
            'total': len(rows), 'offset': offset, 'limit': limit, 'has_more': offset + limit < len(rows),
            'counts': counts, 'positions': positions, 'max_marks': MAX_MARKS, 'query': query}


def add_mark(db, account_id, position, question_id, trees, bank):
    lock_account(db, account_id)
    existing = db.scalar(select(QuestionMark).where(QuestionMark.account_id == account_id,
        QuestionMark.position == position, QuestionMark.question_id == question_id))
    if existing:
        return {'id': existing.id, 'reused': True}  # 重复收藏不重置状态、时间或版本。
    if position not in trees or not any(q.position == position and q.id == question_id for q in bank.questions):
        raise HTTPException(404, '当前题库没有这道题，无法新增收藏')
    count = db.scalar(select(func.count()).select_from(QuestionMark).where(QuestionMark.account_id == account_id))
    if count >= MAX_MARKS:
        raise HTTPException(409, '个人题单最多500道，请先移除部分收藏')
    row = QuestionMark(account_id=account_id, position=position, question_id=question_id,
                       status='todo', version=0, created_at=now_utc())
    db.add(row)
    db.flush()
    return {'id': row.id, 'reused': False}


def owned_mark(db, account_id, mark_id, expected_version):
    lock_account(db, account_id)
    row = db.scalar(select(QuestionMark).where(QuestionMark.id == mark_id, QuestionMark.account_id == account_id))
    if row is None:
        raise HTTPException(404, '收藏不存在')
    if row.version != expected_version:
        raise HTTPException(409, '题单已在其他页面更新，请刷新后再操作')
    return row


def update_mark(db, account_id, mark_id, status, expected_version):
    row = owned_mark(db, account_id, mark_id, expected_version)
    if row.status != status:
        row.status = status
        row.reviewed_at = now_utc() if status == 'done' else None
        row.version += 1
    return {'id': row.id, 'status': row.status, 'version': row.version}
