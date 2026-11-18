"""Assistant API: owner checks, bounded histories, optimistic turns and SSE."""
from datetime import timedelta
from contextvars import copy_context
import json
import threading
import uuid
import anyio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.factories import load_assets
from app.models.entities import Account, AssistantConversation
from app.security import sanitize_pii
from app.services.accounts import (AuthThrottle, account_for_token, bearer_token,
    lock_account, now_utc, require_account)
from app.services.assistant import respond
from app.services.practice_focus import latest_practice_focus

router = APIRouter(prefix='/api/assistant', tags=['assistant'])
throttle = AuthThrottle()
capacity = threading.BoundedSemaphore(2)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ConversationInput(Input):
    position: str = Field(min_length=1, max_length=64)


class TurnInput(Input):
    text: str = Field(min_length=1, max_length=1200)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_version: int = Field(strict=True, ge=0)
    include_focus: bool = Field(default=False, strict=True)

    @field_validator('text')
    @classmethod
    def meaningful(cls, text):
        if not text.strip():
            raise ValueError('Empty message')
        return sanitize_pii(text.strip())


class DemoInput(Input):
    position: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=1200)


class RenameInput(Input):
    title: str = Field(min_length=1, max_length=60)
    expected_version: int = Field(strict=True, ge=0)


def rate_limit(request: Request):
    try:
        throttle.check(request.client.host if request.client else 'unknown')
    except HTTPException:
        raise HTTPException(429, '提问较频繁，请稍等一分钟再继续。', headers={'Retry-After': '60'}) from None


def assets(position):
    settings = get_settings()
    trees, bank = load_assets(settings)
    if position not in trees or not any(q.position == position for q in bank):
        raise HTTPException(422, '请选择可用的练习方向。')
    return settings, trees, bank


def owned(db, identity, account_id):
    row = db.scalar(select(AssistantConversation).where(AssistantConversation.id == identity,
        AssistantConversation.account_id == account_id))
    if row is None:
        raise HTTPException(404, '对话不存在或已被删除。')
    return row


def serialize(row, full=True):
    result = {'id': row.id, 'title': row.title, 'position': row.position,
              'version': row.version, 'updated_at': row.updated_at.isoformat() + 'Z'}
    if full:
        result['messages'] = row.messages
    return result


def event(value):
    return 'data: ' + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n\n'


def stream_response(iterator):
    async def stable_context():
        # Starlette schedules successive sync next() calls in different contexts.
        # Keep ContextVar budgets in one context and close on disconnect as well.
        context = copy_context()
        sentinel = object()
        def advance():
            return next(iterator, sentinel)
        try:
            while True:
                value = await anyio.to_thread.run_sync(context.run, advance)
                if value is sentinel:
                    break
                yield value
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(context.run, iterator.close)
    return StreamingResponse(stable_context(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.get('/conversations')
def conversations(db: Session = Depends(get_db), account: Account = Depends(require_account)):
    rows = db.scalars(select(AssistantConversation).where(AssistantConversation.account_id == account.id)
        .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id.desc()).limit(20))
    return {'items': [serialize(row, False) for row in rows], 'limit': 20}


@router.post('/conversations', dependencies=[Depends(rate_limit)])
def create(payload: ConversationInput, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    assets(payload.position)
    lock_account(db, account.id)
    if db.scalar(select(func.count()).select_from(AssistantConversation).where(AssistantConversation.account_id == account.id)) >= 20:
        raise HTTPException(409, '最多保留20个对话，请先删除不再需要的对话。')
    row = AssistantConversation(account_id=account.id, position=payload.position, updated_at=now_utc())
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.get('/conversations/{identity}')
def detail(identity: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return serialize(owned(db, identity, account.id))


def mutable(row, version):
    if row.version != version:
        raise HTTPException(409, '对话已更新，请重新打开后继续。')
    if row.busy_until and row.busy_until > now_utc():
        raise HTTPException(409, '这段对话正在回答，请稍候再操作。')


@router.patch('/conversations/{identity}')
def rename(identity: str, payload: RenameInput, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    lock_account(db, account.id)
    row = owned(db, identity, account.id)
    mutable(row, payload.expected_version)
    title = sanitize_pii(payload.title.strip())
    if not title:
        raise HTTPException(422, '请输入对话名称。')
    row.title, row.version, row.updated_at = title, row.version + 1, now_utc()
    db.commit()
    return serialize(row)


@router.delete('/conversations/{identity}')
def remove(identity: str, expected_version: int = Query(ge=0), db: Session = Depends(get_db), account: Account = Depends(require_account)):
    lock_account(db, account.id)
    row = owned(db, identity, account.id)
    mutable(row, expected_version)
    db.delete(row)
    db.commit()
    return {'deleted': True}


@router.post('/demo', dependencies=[Depends(rate_limit)])
def demo(payload: DemoInput, account: Account = Depends(require_account)):
    settings, trees, bank = assets(payload.position)
    if not payload.text.strip():
        raise HTTPException(422, '请输入想了解的问题。')
    def generate():
        yield from (event(item) for item in respond(settings, trees, bank, position=payload.position,
            text=payload.text, allow_model=False))
        yield event({'type': 'done', 'version': 0})
    return stream_response(generate())


@router.post('/conversations/{identity}/turns', dependencies=[Depends(rate_limit)])
def turn(identity: str, payload: TurnInput, db: Session = Depends(get_db),
         account: Account = Depends(require_account), authorization: str | None = Header(default=None)):
    row = owned(db, identity, account.id)
    # A response lost after commit can be retrieved without another model charge.
    for index in range(0, len(row.messages), 2):
        if row.messages[index].get('request_id') == payload.request_id:
            if row.messages[index]['content'] != payload.text:
                raise HTTPException(409, '该消息标识已被使用，请重新打开对话。')
            answer = row.messages[index + 1]
            replay = [{'type': 'evidence', **answer['evidence']}, {'type': 'delta', 'text': answer['content']},
                {'type': 'mode', **answer['mode']}, {'type': 'done', 'version': row.version, 'replayed': True}]
            return stream_response(iter(event(item) for item in replay))
    mutable(row, payload.expected_version)
    if len(row.messages) >= 40:
        raise HTTPException(409, '这段对话已达到20轮，请新建对话继续。')
    settings, trees, bank = assets(row.position)
    focus = latest_practice_focus(db, account.id, trees, settings.weak_score) if payload.include_focus else None
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, '小青正在处理其他提问，请稍后重试。')
    busy_id = uuid.uuid4().hex
    account_id, token = account.id, bearer_token(authorization)
    position, history, title = row.position, list(row.messages), row.title
    engine = db.get_bind()
    try:
        changed = db.execute(update(AssistantConversation).where(AssistantConversation.id == identity,
            AssistantConversation.account_id == account_id, AssistantConversation.version == payload.expected_version,
            or_(AssistantConversation.busy_until.is_(None), AssistantConversation.busy_until <= now_utc()))
            .values(busy_id=busy_id, busy_until=now_utc() + timedelta(seconds=120))).rowcount
        if not changed:
            raise HTTPException(409, '对话已更新或正在回答，请重新打开后继续。')
        db.commit()
    except BaseException:
        capacity.release()
        raise

    def generate():
        parts, evidence, mode, failed = [], {}, {}, False
        workflow = respond(settings, trees, bank, position=position, text=payload.text,
            history=history, focus=focus, include_focus=payload.include_focus)
        try:
            for item in workflow:
                if item['type'] == 'delta':
                    parts.append(item['text'])
                elif item['type'] == 'revision':
                    parts[:] = [item['text']]
                elif item['type'] == 'evidence':
                    evidence = {key: value for key, value in item.items() if key != 'type'}
                elif item['type'] == 'mode':
                    mode = {key: value for key, value in item.items() if key != 'type'}
                elif item['type'] == 'error':
                    failed = True
                yield event(item)
            if failed or not parts:
                return
            with Session(engine) as writer:
                current = account_for_token(writer, token)
                if current is None or current.id != account_id:
                    yield event({'type': 'error', 'message': '登录已变化，回答未保存，请重新登录。'})
                    return
                messages = history + [{'role': 'user', 'content': payload.text, 'request_id': payload.request_id},
                    {'role': 'assistant', 'content': sanitize_pii(''.join(parts)), 'evidence': evidence, 'mode': mode}]
                updated = writer.execute(update(AssistantConversation).where(AssistantConversation.id == identity,
                    AssistantConversation.account_id == account_id, AssistantConversation.busy_id == busy_id)
                    .values(messages=messages, title=payload.text[:40] if not history else title,
                        version=payload.expected_version + 1, updated_at=now_utc(), busy_id=None, busy_until=None)).rowcount
                writer.commit()
                if not updated:
                    yield event({'type': 'error', 'message': '对话状态已变化，回答未保存，请重新打开。'})
                    return
            yield event({'type': 'done', 'version': payload.expected_version + 1})
        except Exception:
            yield event({'type': 'error', 'message': '回答暂未完成，请重新打开对话后重试。'})
        finally:
            try:
                workflow.close()
            finally:
                try:
                    with Session(engine) as writer:
                        writer.execute(update(AssistantConversation).where(AssistantConversation.id == identity,
                            AssistantConversation.busy_id == busy_id).values(busy_id=None, busy_until=None))
                        writer.commit()
                finally:
                    capacity.release()
    return stream_response(generate())
