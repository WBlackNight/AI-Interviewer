"""有归属校验的实时陪练入口；单次有界会话，不自动重连。"""
import asyncio
import json
import re
import time
from anyio import CancelScope

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Header, HTTPException
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.db import SessionLocal
from app.repositories import get_interview
from app.models.entities import InterviewRuntime
from app.security import has_access
from app.voice.doubao import DoubaoVoiceError, DoubaoVoiceOptions
from app.voice.realtime import RealtimeDialogue

router = APIRouter()


def public_error_code(error):
    """Only stable local categories reach the browser; never forward provider messages."""
    if isinstance(error, DoubaoVoiceError):
        if str(error) == 'capacity':
            return 'capacity'
        if error.http_status in (401, 403) or str(error) in ('credentials_missing', 'legacy_credentials_missing'):
            return 'provider_auth'
        if str(error) in ('session_timeout', 'receive_timeout'):
            return 'provider_timeout'
    if isinstance(error, asyncio.TimeoutError):
        return 'provider_timeout'
    return 'realtime_unavailable'


def current_context(db, interview_id, token):
    if not has_access(db, 'interview', interview_id, token):
        raise HTTPException(403, '面试访问凭据无效')
    interview = get_interview(db, interview_id)
    if not interview or interview.status in ('finished', 'cancelled'):
        raise HTTPException(409, '本场已结束，请返回正式练习')
    runtime = db.get(InterviewRuntime, interview_id)
    question = (runtime.snapshot or {}).get('question_event') if runtime else None
    context = {'question': {'content': question['content'][:2000], 'theme': question.get('theme', '')[:100]} if question else None}
    if context['question'] and interview.position == 'english_interview':
        context['question']['language'] = 'en'
    return context


@router.get('/api/interview/{interview_id}/realtime-context')
def realtime_context(interview_id: str, token: str | None = Header(default=None, alias='X-Interview-Token')):
    # 仅查询当前题，不读取简历、答案、评分或创建供应商连接。
    with SessionLocal() as db:
        return JSONResponse(current_context(db, interview_id, token), headers={'Cache-Control': 'no-store'})


@router.websocket('/ws/realtime/{interview_id}')
async def realtime_ws(websocket: WebSocket, interview_id: str):
    settings = get_settings()
    protocols = websocket.scope.get('subprotocols', [])
    token = protocols[1] if len(protocols) == 2 and protocols[0] == 'interview' else None

    def authorized():
        with SessionLocal() as db:
            if not has_access(db, 'interview', interview_id, token):
                return False
            interview = get_interview(db, interview_id)
            return bool(interview and interview.status not in ('finished', 'cancelled'))

    if (not re.fullmatch('[a-f0-9]{32}', interview_id) or not authorized()
            or websocket.headers.get('origin') not in settings.cors_origins):
        await websocket.close(code=4403)
        return
    await websocket.accept(subprotocol='interview')
    if not settings.voice_enabled or (settings.voice_asr_provider, settings.voice_tts_provider) != ('doubao', 'doubao'):
        await websocket.send_json({'type': 'error', 'code': 'realtime_disabled'})
        await websocket.close(code=1000)
        return
    dialogue = RealtimeDialogue(DoubaoVoiceOptions.from_settings(settings))
    send_lock = asyncio.Lock()

    async def send(event):
        async with send_lock:
            await asyncio.wait_for(websocket.send_json(event), 3)

    async def receive_client():
        start, frames, controls = time.monotonic(), 0, 0
        while True:
            # 陪练可暂停收音等待下一轮，整场时限由外层统一控制。
            raw = await websocket.receive_text()
            if len(raw.encode()) > 5000 or not authorized():
                raise DoubaoVoiceError('access_or_size')
            if time.monotonic() - start >= 60:
                start, frames, controls = time.monotonic(), 0, 0
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise DoubaoVoiceError('invalid_message')
            if event.get('type') == 'audio':
                frames += 1
            else:
                controls += 1
            if frames > settings.voice_max_frames_per_minute or controls > 60:
                raise DoubaoVoiceError('rate_limit')
            await dialogue.accept(event)

    async def receive_provider():
        while True:
            try:
                event = await dialogue.session.receive()
            except DoubaoVoiceError as exc:
                if str(exc) == 'receive_timeout':
                    continue
                raise
            if not authorized():
                raise DoubaoVoiceError('access_revoked')
            translated = dialogue.translate(event)
            if translated:
                await send(translated)

    tasks = []
    try:
        with SessionLocal() as db:
            context = current_context(db, interview_id, token)
        await dialogue.start(context.get('question'))
        await send({'type': 'ready', 'max_seconds': dialogue.limit, 'question': context.get('question')})
        tasks = [asyncio.create_task(receive_client()), asyncio.create_task(receive_provider())]
        done, _ = await asyncio.wait(tasks, timeout=dialogue.limit, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        await send({'type': 'ended'})
    except WebSocketDisconnect:
        pass
    except (DoubaoVoiceError, asyncio.TimeoutError, ValueError, TypeError, RuntimeError, HTTPException) as error:
        try:
            await send({'type': 'error', 'code': public_error_code(error)})
        except Exception:
            pass
    finally:
        # 浏览器离页或ASGI取消也必须完成供应商连接关闭。
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await dialogue.close()
            try:
                await websocket.close(code=1000)
            except RuntimeError:
                pass
