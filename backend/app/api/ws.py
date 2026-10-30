"""面试 WebSocket：鉴权、严格输入、轮次提交与语音链路（P1）。

三任务架构（评审要求，见 docs/技术实现步骤.md 步骤 1.4）：

1. **接收任务**（本文件的 ``while`` 循环）：只做校验与路由，
   **不阻塞在业务处理上**；
2. **业务处理任务**：每轮一个后台协程，经 ``asyncio.to_thread`` 调用同步的
   ``process_message``；
3. **音频发送任务**：``PlaybackController`` 内部的发送协程，从有界队列取分片下发。

为什么必须拆：旧实现 ``await process_message`` 会占住接收循环，长评分期间
无法及时收到 ``interrupt``，打断形同虚设。同时按评审要求，
``asyncio.to_thread`` 的取消**不会**强制终止线程内的同步调用，
因此这里不用"强杀线程"，而是给每轮挂一个**取消令牌**：
令牌一旦被取消，该轮的结果按"过期结果"丢弃并落库，不会污染会话。

文字模式行为保持与既有版本一致（含 ``interrupt`` 的提示语），
语音能力仅在 ``VOICE_ENABLED=true`` 时启用。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.agent.session import InterviewSession, AssetVersionError
from app.agent.state_machine import InterviewState
from app.config import get_settings
from app.db import SessionLocal
from app.domain import EventType, PlanItem, VoiceRecordType
from app.factories import (
    build_llm,
    build_prober,
    build_scorer,
    build_sandbox,
    build_tts,
    build_voice_channel,
    load_assets,
)
from app.models.entities import InterviewRuntime, InterviewSubmission
from app.repositories import (
    append_system_event,
    commit_turn,
    get_interview,
    load_events,
    ConcurrentTurnError,
    cancelled_snapshot,
)
from app.schemas import (
    AnswerMessage,
    AudioEndMessage,
    AudioMessage,
    InterruptMessage,
    StartMessage,
    ReadQuestionMessage,
    incoming_message,
)
from app.security import has_access, sanitize_pii
from app.llm.budget import use_budget
from app.llm.errors import BudgetExceeded
from app.llm.persistent_budget import PersistentBudget
from app.sandbox.judge0 import SandboxUnavailable
from app.voice.channel import VoiceChannel
from app.voice.playback import CancelToken, PlaybackController

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

#: turn_id 的格式约束（与 schemas.AnswerMessage 保持一致）。
_TURN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class SessionManager:
    """仅管理运行中的锁；业务状态每轮从数据库恢复，空闲后立即清理。"""
    def __init__(self):
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def locked(self, interview_id):
        lock, users = self._locks.get(interview_id, (asyncio.Lock(), 0))
        self._locks[interview_id] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            _, users = self._locks[interview_id]
            if users == 1:
                del self._locks[interview_id]
            else:
                self._locks[interview_id] = (lock, users - 1)


manager = SessionManager()


def error(detail: str, code: str, *, retryable: bool = False) -> list[dict]:
    return [{"type": "error", "detail": detail, "code": code, "retryable": retryable}]


class WSender:
    """串行化发送。

    业务事件、音频分片、错误提示来自不同协程；不串行化会在传输层交错，
    表现为客户端收到半截 JSON 或音频帧顺序错乱。
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._lock = asyncio.Lock()
        self.closed = False

    async def send(self, event: dict) -> None:
        async with self._lock:
            if self.closed:
                return
            try:
                await self._ws.send_json(event)
            except Exception:
                self.closed = True
                raise

    async def send_many(self, events: list[dict]) -> None:
        for event in events:
            await self.send(event)


def load_session(interview, runtime) -> InterviewSession:
    trees, bank = load_assets(settings)
    tree = trees[interview.position]
    llm = build_llm(settings)
    session = InterviewSession(
        interview_id=interview.id, position=interview.position,
        plan=[PlanItem(**p) for p in interview.plan], bank=bank,
        scorer=build_scorer(settings, llm), prober=build_prober(settings, llm, tree),
        pass_score=settings.pass_score, probe_score=settings.probe_score,
        probe_depth_limit=settings.probe_depth_limit, sandbox=build_sandbox(settings),
    )
    session._owned_llm = llm
    if runtime and runtime.snapshot:
        try:
            session.restore(runtime.snapshot)
        except Exception:
            if hasattr(llm, "close"):
                llm.close()
            raise
    if interview.status == "finished":
        session.finished = True
        session.state = InterviewState.FINISHED
    return session


def snapshot_event(db, interview, runtime, session):
    events = [e.payload for e in load_events(db, interview.id)]
    current = session.current_question
    if current:
        current = next((e for e in reversed(events) if e.get("type") == "question"
                        and e.get("turn_id") == current["turn_id"]), current)
    return [{"type": "snapshot", "state": session.state.value,
             "finished": session.finished, "version": runtime.version if runtime else 0,
             "current_question": current, "events": events}]


def process_message(interview_id: str, message, credential: str | None = None) -> list[dict]:
    started = time.monotonic()
    session = None
    try:
        # 加载阶段不跨供应商调用持有数据库事务/连接。
        with SessionLocal() as db:
            if credential is not None and not has_access(db, "interview", interview_id, credential):
                return error("访问授权已失效，请重新登录或刷新", "access_revoked")
            interview = get_interview(db, interview_id)
            if interview is None:
                return error("面试不存在", "not_found")
            if interview.status == "cancelled":
                return cancelled_snapshot(db, interview_id)
            runtime = db.get(InterviewRuntime, interview_id)
            if isinstance(message, AnswerMessage):
                request_hash = hashlib.sha256(message.model_dump_json().encode()).hexdigest()
                previous = db.get(InterviewSubmission, (interview_id, message.message_id))
                if previous:
                    if previous.request_hash != request_hash:
                        return error("相同消息编号不能用于不同回答", "message_conflict")
                    return previous.events
            session = load_session(interview, runtime)
            if isinstance(message, StartMessage) and (session.finished or runtime and runtime.snapshot):
                return snapshot_event(db, interview, runtime, session)
            if runtime is None or interview.status == "running" and not runtime.snapshot:
                return error("旧面试没有恢复快照，请创建新面试", "legacy_session")
            version = runtime.version
        if isinstance(message, StartMessage):
            events = session.start()
        elif isinstance(message, AnswerMessage):
            if session.finished:
                return error("面试已结束", "finished")
            question = session.current_question
            if not question or message.turn_id != question["turn_id"] or message.version != version:
                return error("当前轮次已更新，请同步后再提交", "stale_turn")
            if message.code and not question.get("is_coding"):
                return error("知识题不接受代码字段", "invalid_answer")
            meter = PersistentBudget(SessionLocal, "interview", interview_id, settings) if session._owned_llm else None
            with use_budget(meter):
                events = session.handle_answer(sanitize_pii(message.text),
                                               code=sanitize_pii(message.code) if message.code else None)
        else:
            return [{"type": "agent_message", "text": "当前为文字模式，请继续回答。"}]
        if any(e["type"] == "error" for e in events):
            return events
        if isinstance(message, AnswerMessage):
            for event in events:
                if event["type"] == "answer_ack":
                    event["message_id"] = message.message_id
        if time.monotonic() - started > settings.turn_timeout_seconds:
            return error("本轮处理超时，请重试", "turn_timeout", retryable=True)
        with SessionLocal() as db:
            if credential is not None and not has_access(db, "interview", interview_id, credential):
                return error("访问授权已失效，本轮未提交", "access_revoked")
            latest = get_interview(db, interview_id)
            if latest is None:
                return error("面试不存在", "not_found")
            if latest.status == "cancelled":
                return cancelled_snapshot(db, interview_id)
            numbered = commit_turn(db, interview_id, version, session.snapshot(), events,
                                   session.drain_records(),
                                   message.message_id if isinstance(message, AnswerMessage) else None,
                                   request_hash if isinstance(message, AnswerMessage) else None)
            if isinstance(message, StartMessage):
                return snapshot_event(db, get_interview(db, interview_id),
                                      db.get(InterviewRuntime, interview_id), session)
            return numbered
    except SandboxUnavailable as exc:
        return error("沙箱暂不可用，本轮未提交，请稍后重试或联系管理员", "sandbox_"+exc.code,
                     retryable=exc.retryable)
    except BudgetExceeded:
        return error("模型预算暂停、耗尽或请求繁忙；本轮未提交，请核对用量后再继续", "llm_budget_blocked")
    except AssetVersionError:
        return error("题库、技能树或检索策略已更新，请恢复原配置或从首页创建新面试", "assets_changed")
    except ConcurrentTurnError:
        with SessionLocal() as db:
            if credential is not None and not has_access(db, "interview", interview_id, credential):
                return error("访问授权已失效", "access_revoked")
            interview = get_interview(db, interview_id)
            if interview and interview.status == "cancelled":
                return cancelled_snapshot(db, interview_id)
        return error("会话已更新，请同步后再提交", "stale_turn")
    except Exception as exc:
        # 不记录第三方响应/回答/凭据，失败状态未提交，下次可以安全重试。
        logger.error("turn_failed interview=%s reason=%s", interview_id, type(exc).__name__)
        return error("本轮处理失败，状态已保留，请重试", "processing_failed", retryable=True)
    finally:
        llm = getattr(session, "_owned_llm", None)
        if hasattr(llm, "close"):
            llm.close()


class InterviewConnection:
    """单条 WS 连接的全部状态与处理逻辑（含语音通道与播放控制器）。"""

    def __init__(self, websocket: WebSocket, interview_id: str, credential: str | None = None) -> None:
        self.interview_id = interview_id
        self.credential = credential
        self.sender = WSender(websocket)
        self.voice_on = bool(settings.voice_enabled)
        self.voice: VoiceChannel | None = build_voice_channel(settings) if self.voice_on else None
        self.playback: PlaybackController | None = (
            PlaybackController(
                build_tts(settings),
                send_event=self.sender.send,
                queue_max=settings.voice_audio_queue_max,
                on_record=self._record,
            )
            if self.voice_on
            else None
        )
        self._turn: asyncio.Task | None = None
        self._token: CancelToken | None = None
        self._speak_task: asyncio.Task | None = None
        self._suppress_tts = False
        self._from_voice = False
        self._last_read = 0.0
        self._voice_version = None
        self._voice_ended_turn: str | None = None

    # ------------------------------------------------------------ 生命周期

    async def setup(self) -> None:
        if self.playback is not None:
            await self.playback.start()

    async def shutdown(self) -> None:
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()
            self._speak_task = None
        if self.voice is not None:
            try:
                await self.voice.close()
            except Exception as exc:
                logger.debug("voice: 关闭通道失败 reason=%s", type(exc).__name__)
        if self.playback is not None:
            try:
                await self.playback.close()
            except Exception as exc:
                logger.debug("voice: 关闭播放失败 reason=%s", type(exc).__name__)

    async def _record(self, event: dict) -> None:
        """语音审计事件落库（评审要求：持久化取消事件及原因）。"""
        event = {**event, "interview_id": self.interview_id}
        try:
            with SessionLocal() as db:
                append_system_event(db, self.interview_id, event)
        except Exception as exc:
            logger.warning("voice: 审计事件落库失败 type=%s reason=%s",
                           event.get("type"), type(exc).__name__)

    # ------------------------------------------------------------ 业务轮次

    async def run_turn(self, message) -> None:
        """后台执行业务轮次；完成后下发事件并按需播报。"""
        token = self._token
        try:
            async with manager.locked(self.interview_id):
                events = await asyncio.to_thread(process_message, self.interview_id, message, self.credential)
        except Exception as exc:  # 兜底：任何异常都不能让连接静默卡住
            logger.error("turn_task_failed interview=%s reason=%s", self.interview_id,
                         type(exc).__name__)
            events = error("本轮处理失败，状态已保留，请重试", "processing_failed", retryable=True)

        if token is not None and token.cancelled:
            # 过期结果：本轮已被打断作废，只记录不下发，避免污染客户端状态。
            await self._record(
                {"type": VoiceRecordType.TURN_DISCARDED, "reason": token.reason or "interrupted"}
            )
            return

        await self.sender.send_many(events)
        self._maybe_speak(events)

    def start_turn(self, message, *, from_voice: bool = False) -> None:
        self._token = CancelToken()
        # 注意：语音来源必须由调用方显式传入。早先这里硬编码 False，
        # 会在语音轮次提交时覆盖调用方刚设置的标记，导致语音不播报。
        self._from_voice = from_voice
        self._turn = asyncio.create_task(self.run_turn(message), name="interview-turn")

    async def _await_turn(self) -> None:
        """同一连接串行处理：新消息到达时先等上一轮结束（保持既有语义）。"""
        if self._turn is not None and not self._turn.done():
            try:
                await asyncio.shield(self._turn)
            except Exception:  # run_turn 内部已兜底，这里只防止向上冒泡
                pass

    def _maybe_speak(self, events: list[dict]) -> None:
        if self.playback is None or self._suppress_tts:
            self._suppress_tts = False
            return
        if not self._from_voice and not settings.voice_tts_text_mode:
            return
        turn_id = next((e.get("turn_id") for e in events if e.get("turn_id")), "")
        # 必须持有引用：否则事件循环可能在播报中途回收该任务。
        self._speak_task = asyncio.create_task(
            self.playback.speak(events, turn_id=str(turn_id)), name="voice-speak"
        )

    # ------------------------------------------------------------ 消息处理

    async def handle(self, message) -> None:
        if isinstance(message, ReadQuestionMessage):
            await self.handle_read_question(message)
        elif isinstance(message, AudioMessage):
            await self.handle_audio(message)
        elif isinstance(message, AudioEndMessage):
            await self.handle_audio_end(message)
        elif isinstance(message, InterruptMessage):
            await self.handle_interrupt(message)
        else:
            await self._await_turn()
            self.start_turn(message)

    async def handle_read_question(self, message: ReadQuestionMessage) -> None:
        if self.playback is None:
            await self.sender.send_many(error("语音未启用", "voice_disabled"))
            return
        if self.playback.playing or time.monotonic() - self._last_read < 5:
            await self.sender.send_many(error("请稍后再次播报", "voice_read_busy"))
            return
        self._last_read = time.monotonic()
        await self._await_turn()
        async with manager.locked(self.interview_id):
            events = await asyncio.to_thread(process_message, self.interview_id, StartMessage(type="start"), self.credential)
        snapshot = next((e for e in events if e.get("type") == "snapshot"), None)
        question = snapshot.get("current_question") if snapshot else None
        if (not question or snapshot.get("finished") or snapshot.get("cancelled")
                or question.get("turn_id") != message.turn_id or snapshot.get("version") != message.version):
            await self.sender.send_many(error("当前题目已更新，请同步后再播报", "stale_turn"))
            return
        await self.playback.speak([question], turn_id=message.turn_id)

    async def handle_audio(self, message: AudioMessage) -> None:
        if self.voice is None:
            await self.sender.send_many(error("语音未启用", "voice_disabled"))
            return
        # 自动判停到客户端收到通知之间，网络中可能仍有同段尾帧。
        # 丢弃已结束发言的连续尾帧，不能将它们重新绑定为 seq=0 的新发言。
        if message.turn_id == self._voice_ended_turn and message.seq > 0:
            return
        if not self.voice.active:
            await self._await_turn()
            with SessionLocal() as db:
                runtime = db.get(InterviewRuntime, self.interview_id)
                interview = get_interview(db, self.interview_id)
                snapshot = runtime.snapshot if runtime else None
                question = snapshot.get("question_event") if snapshot else None
                valid = (interview and interview.status == "running" and question
                         and not snapshot.get("finished") and not question.get("is_coding")
                         and question.get("turn_id") == message.turn_id)
                self._voice_version = runtime.version if valid else None
            if not valid:
                await self.sender.send_many(error("当前轮次不接受语音，请同步或使用文字", "stale_turn"))
                return
            self._voice_ended_turn = None
        result = await self.voice.feed(message.data, turn_id=message.turn_id, seq=message.seq)
        if result.error:
            await self.sender.send_many(error(result.error, "voice_invalid"))
        await self.sender.send_many(result.events)
        if result.speech_started:
            # 用户开口 → 打断当前播报（barge-in）。
            await self._barge_in(trigger="speech_detected")
        if result.utterance_ended:
            await self._finish_utterance(trigger="vad")

    async def handle_audio_end(self, message: AudioEndMessage) -> None:
        if self.voice is None:
            await self.sender.send_many(error("语音未启用", "voice_disabled"))
            return
        if self.voice.turn_id is not None and self.voice.turn_id != message.turn_id:
            await self.sender.send_many(error("turn 不匹配，请先同步会话", "stale_turn"))
            return
        await self._finish_utterance(trigger="client_end")

    async def _finish_utterance(self, *, trigger: str) -> None:
        assert self.voice is not None
        # 必须在 finish() 之前取 turn_id —— finish 会清空发言绑定。
        turn_id = self.voice.turn_id or ""
        if turn_id:
            self._voice_ended_turn = turn_id
            await self.sender.send({"type": "voice_processing", "turn_id": turn_id})
        text, events = await self.voice.finish()
        await self.sender.send_many(events)
        if not text:
            return
        if not _TURN_ID_PATTERN.fullmatch(turn_id):
            # 没有有效 turn 绑定就无法安全提交（会被 AnswerMessage 校验拒绝）。
            await self.sender.send_many(
                error("语音缺少有效的轮次绑定，请重新同步会话后重试", "stale_turn")
            )
            return
        await self._await_turn()
        message = self._voice_answer(turn_id, text)
        self.start_turn(message, from_voice=True)
        logger.info("voice: 提交语音轮次 turn=%s trigger=%s", turn_id, trigger)

    def _voice_answer(self, turn_id: str, text: str) -> AnswerMessage:
        """把识别文本包装成与文字模式完全等价的 ``answer`` 消息。

        复用既有 turn 流程 → 幂等、版本校验、PII 脱敏、事件落库全部继承，
        语音链路不需要第二套提交逻辑。
        """
        with SessionLocal() as db:
            runtime = db.get(InterviewRuntime, self.interview_id)
            version = self._voice_version if self._voice_version is not None else runtime.version if runtime else 0
        return AnswerMessage(
            type="answer",
            message_id=f"voice-{uuid.uuid4().hex[:20]}",
            turn_id=turn_id,
            version=version,
            text=text,
        )

    async def handle_interrupt(self, message: InterruptMessage) -> None:
        if self.playback is None:
            # 语音关闭：保持既有文字模式提示（README 与冒烟脚本依赖该行为）。
            await self.sender.send_many(
                [{"type": "agent_message", "text": "当前为文字模式，请继续回答。"}]
            )
            return
        cancelled = await self._barge_in(trigger="client_interrupt")
        if cancelled is None:
            # 没有正在播放的语音：也要回应，否则客户端会一直等 ACK。
            await self.sender.send_many(
                [{"type": EventType.BARGE_IN_ACK, "utterance_id": None,
                  "note": "没有正在播放的语音"}]
            )

    async def _barge_in(self, *, trigger: str) -> str | None:
        """取消当前播报。返回被取消的 utterance_id。"""
        if self.playback is None:
            return None
        utterance_id = await self.playback.interrupt(reason=trigger)
        if self._turn is not None and not self._turn.done():
            # 业务轮次仍在进行：标记"不要播报本轮结果"。
            # 用标志位而非强杀线程 —— to_thread 的取消不会终止同步调用，
            # 强行 cancel 只会留下无法回收的线程与未关闭的连接。
            self._suppress_tts = True
            if self._token is not None:
                self._token.cancel(trigger)
        if utterance_id is not None:
            await self.sender.send_many(
                [{"type": EventType.BARGE_IN_ACK, "utterance_id": utterance_id}]
            )
        return utterance_id


@router.websocket("/ws/interview/{interview_id}")
async def interview_ws(websocket: WebSocket, interview_id: str) -> None:
    origin = websocket.headers.get("origin")
    protocols = websocket.scope.get("subprotocols", [])
    token = protocols[1] if len(protocols) == 2 and protocols[0] == "interview" else None
    with SessionLocal() as db:
        authorized = has_access(db, "interview", interview_id, token)
    if not authorized or origin and origin not in settings.cors_origins:
        await websocket.close(code=4403)
        return
    await websocket.accept(subprotocol="interview")

    conn = InterviewConnection(websocket, interview_id, token)
    await conn.setup()
    failures = 0
    window_start, received, frames = time.monotonic(), 0, 0
    try:
        while True:
            frame = await asyncio.wait_for(websocket.receive(), settings.ws_idle_timeout_seconds)
            if frame["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(frame.get("code", 1000))
            with SessionLocal() as db:
                authorized = has_access(db, "interview", interview_id, token)
                interview = get_interview(db, interview_id) if authorized else None
                terminal = cancelled_snapshot(db, interview_id) if interview and interview.status == "cancelled" else None
            if not authorized:
                await conn.sender.send(error("访问授权已失效，请重新登录", "access_revoked")[0])
                await websocket.close(code=4403)
                return
            if terminal:
                await conn.sender.send_many(terminal)
                await websocket.close(code=1000)
                return
            if time.monotonic() - window_start >= 60:
                window_start, received, frames = time.monotonic(), 0, 0
            raw = frame.get("text")
            if not isinstance(raw, str):
                await conn.sender.send(error("文字模式只接收JSON文本", "invalid_message")[0])
                continue
            if len(raw.encode()) > settings.ws_max_message_bytes:
                await conn.sender.send(error("消息超过长度上限", "invalid_message")[0])
                await websocket.close(code=1009)
                return
            try:
                message = incoming_message.validate_json(raw)
            except ValidationError:
                failures += 1
                await conn.sender.send(error("消息格式或字段非法", "invalid_message")[0])
                if failures >= 10:
                    await websocket.close(code=1008)
                    return
                continue

            # 音频帧与普通消息使用**独立的频率预算**：10 帧/秒是语音常态，
            # 共用 60 条/分钟的文字限流会让语音在 6 秒后被误杀。
            if isinstance(message, AudioMessage):
                frames += 1
                if frames > settings.voice_max_frames_per_minute:
                    await conn.sender.send(
                        error("音频帧过于频繁，请稍后重连", "rate_limit")[0]
                    )
                    await websocket.close(code=1008)
                    return
            else:
                received += 1
                if received > 60:
                    await conn.sender.send(error("消息过于频繁，请稍后重连", "rate_limit")[0])
                    await websocket.close(code=1008)
                    return

            await conn.handle(message)
            # 保持连接便于重试终轮 message_id；客户端看到 finished 后主动断开。
    except asyncio.TimeoutError:
        await websocket.close(code=1000)
    except (WebSocketDisconnect, RuntimeError):
        logger.info("客户端断开 interview=%s", interview_id)
    finally:
        await conn.shutdown()
