"""Seeduplex JSON适配：只取用户转写，播报本项目确定的文本；不执行工具调用。"""
from __future__ import annotations

import asyncio
import base64
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
import json
import logging
import re
from threading import Lock
import uuid

from websockets.asyncio.client import connect

from app.voice.asr import Transcript

ENDPOINT = "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
MAX_EVENT_BYTES = 262144
MAX_TEXT_CHARS = 20000
_lock = Lock()
_active = 0
_counts = Counter()
_logger = logging.getLogger("doubao.voice.transport")
_logger.setLevel(logging.WARNING)


class DoubaoVoiceError(RuntimeError):
    """仅携带固定类别，不携带供应商响应、转写、请求头或异常正文。"""

    def __init__(self, code, *, http_status=None, request_id=None):
        super().__init__(code)
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.request_id = request_id if isinstance(request_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id) else None


@dataclass(frozen=True)
class DoubaoVoiceOptions:
    api_key: str = field(default="", repr=False)
    model: str = "1.2.6.1"
    speaker: str = "zh_female_xiaohe_jupiter_bigtts"
    timeout: float = 15
    session_seconds: float = 120
    max_connections: int = 2
    auth_mode: str = "api_key"
    app_id: str | None = field(default=None, repr=False)
    access_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_settings(cls, settings):
        return cls(api_key=settings.doubao_voice_api_key or "", model=settings.doubao_voice_model,
                   speaker=settings.doubao_voice_speaker, timeout=settings.doubao_voice_timeout_seconds,
                   session_seconds=settings.doubao_voice_session_seconds, max_connections=settings.doubao_voice_max_connections,
                   auth_mode=settings.doubao_voice_auth_mode, app_id=settings.doubao_voice_app_id,
                   access_token=settings.doubao_voice_access_token)

    def headers(self):
        # 旧控制台使用APP ID和Access Token，App-Key为官方协议常量，不使用用户Secret Key。
        if self.auth_mode == "legacy":
            if not self.app_id or not (self.access_token or "").strip():
                raise DoubaoVoiceError("legacy_credentials_missing")
            return {"X-Api-App-Id": self.app_id, "X-Api-Access-Key": self.access_token,
                    "X-Api-Resource-Id": "volc.speech.dialog", "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
                    "X-Api-Request-Id": str(uuid.uuid4())}
        if self.auth_mode != "api_key" or not self.api_key.strip():
            raise DoubaoVoiceError("credentials_missing")
        return {"X-Api-Key": self.api_key}


def diagnostics():
    with _lock:
        return {"active_connections": _active, "counts": dict(_counts),
                "quality_verified": False, "usage_billing_verified": False}


class DuplexSession:
    """有界连接；每次识别/每句播报独立会话，取消不自动重连或重发计费请求。"""

    def __init__(self, options: DoubaoVoiceOptions, *, kind: str):
        self.options = options
        self.kind = kind
        self.ws = None
        self._admitted = False
        self._deadline = 0.0

    async def start(self, *, instructions=None):
        global _active
        headers = self.options.headers()
        with _lock:
            if _active >= self.options.max_connections:
                raise DoubaoVoiceError("capacity")
            _active += 1
            self._admitted = True
            _counts[self.kind + "_attempts"] += 1
        self._deadline = asyncio.get_running_loop().time() + self.options.session_seconds
        try:
            self.ws = await asyncio.wait_for(connect(ENDPOINT, additional_headers=headers,
                open_timeout=self.options.timeout, close_timeout=2, max_size=MAX_EVENT_BYTES,
                max_queue=8, ping_interval=20, ping_timeout=20, logger=_logger), self.options.timeout)
            await self.send("session.create", session={
                "id": str(uuid.uuid4()), "model": self.options.model,
                "instructions": instructions or "你是语音传输助手。不要调用工具，不要自行出题或评分。",
                "audio": {"input": {"format": {"type": "pcm", "rate": 16000}},
                          "output": {"format": {"type": "pcm_s16le", "rate": 24000},
                                     "voice": self.options.speaker}}, "tools": []},
                extension={"tts": {"audio_config": {"channel": 1, "format": "pcm_s16le", "sample_rate": 24000}}})
            for _ in range(32):
                event = await self.receive()
                if event["type"] == "session.created":
                    return
            raise DoubaoVoiceError("session_ack_missing")
        except BaseException as exc:
            await self.close()
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, DoubaoVoiceError):
                raise
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            try:
                request_id = response.headers.get("X-Tt-Logid") if response is not None else None
            except Exception:
                request_id = None
            if isinstance(request_id, str) and any(value and value in request_id for value in (self.options.api_key, self.options.access_token)):
                request_id = None
            code = "auth" if status in (401, 403) else "rate_limit" if status == 429 else "connect"
            raise DoubaoVoiceError(code, http_status=status, request_id=request_id) from None

    def remaining(self):
        value = min(self.options.timeout, self._deadline - asyncio.get_running_loop().time())
        if value <= 0:
            raise DoubaoVoiceError("session_timeout")
        return value

    async def send(self, kind: str, **payload):
        if self.ws is None:
            raise DoubaoVoiceError("not_connected")
        try:
            await asyncio.wait_for(self.ws.send(json.dumps({"type": kind, "event_id": uuid.uuid4().hex,
                                                          **payload}, ensure_ascii=False)), self.remaining())
        except asyncio.CancelledError:
            raise
        except Exception:
            raise DoubaoVoiceError("send") from None

    async def receive(self):
        try:
            raw = await asyncio.wait_for(self.ws.recv(), self.remaining())
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_EVENT_BYTES:
                raise DoubaoVoiceError("event_size_or_type")
            event = json.loads(raw)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise DoubaoVoiceError("event_shape")
            if event["type"] in ("error", "conversation.item.input_audio_transcription.failed"):
                raise DoubaoVoiceError("provider_error")
            if event["type"] == "session.closed":
                raise DoubaoVoiceError("session_closed")
            return event
        except asyncio.CancelledError:
            raise
        except DoubaoVoiceError:
            raise
        except asyncio.TimeoutError:
            raise DoubaoVoiceError("receive_timeout") from None
        except Exception:
            raise DoubaoVoiceError("receive") from None

    def record(self, suffix):
        with _lock:
            _counts[self.kind + "_" + suffix] += 1

    async def close(self):
        global _active
        ws, self.ws = self.ws, None
        try:
            if ws is not None:
                try:
                    await asyncio.wait_for(ws.send(json.dumps({"type": "session.close", "event_id": uuid.uuid4().hex})), 1)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(ws.close(), 3)
                except Exception:
                    pass
        finally:
            if self._admitted:
                self._admitted = False
                with _lock:
                    _active -= 1


class DoubaoASR:
    """后台持续接收转写；partial覆盖显示，finish只消费一次完整结果。"""

    def __init__(self, options: DoubaoVoiceOptions):
        self.options = options
        self.session = None
        self.reader = None
        self._texts = OrderedDict()
        self._final = None
        self._error = None
        self._ready = asyncio.Event()
        self._consumed = False
        self._sent_bytes = 0

    async def start(self):
        await self.close()
        self._texts.clear()
        self._final = self._error = None
        self._ready = asyncio.Event()
        self._consumed = False
        self._sent_bytes = 0
        self.session = DuplexSession(self.options, kind="asr")
        await self.session.start()
        self.reader = asyncio.create_task(self._receive(), name="doubao-asr")

    async def _receive(self):
        try:
            for _ in range(10000):
                event = await self.session.receive()
                kind = event["type"]
                if kind not in ("conversation.item.input_audio_transcription.delta",
                                "conversation.item.input_audio_transcription.completed"):
                    continue
                item = event.get("item_id") or "utterance"
                if not isinstance(item, str) or len(item) > 128 or len(self._texts) >= 16 and item not in self._texts:
                    raise DoubaoVoiceError("transcript_items")
                text = event.get("delta", "") if kind.endswith(".delta") else event.get("transcript", event.get("text", ""))
                if not isinstance(text, str):
                    raise DoubaoVoiceError("transcript_shape")
                self._texts[item] = self._texts.get(item, "") + text if kind.endswith(".delta") else text
                combined = "".join(self._texts.values())
                if len(combined) > MAX_TEXT_CHARS:
                    raise DoubaoVoiceError("transcript_size")
                if kind.endswith(".completed"):
                    self._final = combined.strip()
                    self._ready.set()
                    return
            raise DoubaoVoiceError("event_limit")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = exc if isinstance(exc, DoubaoVoiceError) else DoubaoVoiceError("asr_receive")
            self._ready.set()

    async def feed(self, pcm: bytes, *, sample_rate: int):
        if sample_rate != 16000 or not pcm or len(pcm) % 2 or len(pcm) > 6400:
            raise DoubaoVoiceError("input_format")
        if self._error:
            raise self._error
        if self.session is None or self._consumed:
            raise DoubaoVoiceError("asr_not_started")
        if self._final is None:
            self._sent_bytes += len(pcm)
            if self._sent_bytes > 16000 * 2 * self.options.session_seconds:
                raise DoubaoVoiceError("input_limit")
            await self.session.send("input_audio_buffer.append", audio=base64.b64encode(pcm).decode("ascii"))
            await asyncio.sleep(0)
        if self._error:
            raise self._error
        text = self._final if self._final is not None else "".join(self._texts.values())
        return [Transcript(text, self._final is not None)] if text else []

    async def finish(self):
        if self._consumed or self.session is None:
            return ""
        self._consumed = True
        try:
            if not self._sent_bytes:
                return ""
            if not self._ready.is_set():
                await self.session.send("input_audio_buffer.commit")
                await self.session.send("input_audio_mute.commit")
                await asyncio.wait_for(self._ready.wait(), self.session.remaining())
            if self._error:
                raise self._error
            if not self._final:
                raise DoubaoVoiceError("empty_transcript")
            self.session.record("completed")
            return self._final
        except asyncio.TimeoutError:
            raise DoubaoVoiceError("asr_timeout") from None
        finally:
            await self.close()

    async def close(self):
        reader, self.reader = self.reader, None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            try:
                await reader
            except (asyncio.CancelledError, Exception):
                pass
        session, self.session = self.session, None
        if session is not None:
            await session.close()


class DoubaoTTS:
    """独立会话播报确定文本，PCM16直通，校验响应边界与总量。"""

    sample_rate = 24000

    def __init__(self, options: DoubaoVoiceOptions):
        self.options = options
        self._sessions = set()

    async def synthesize(self, text):
        if not text.strip() or len(text) > 2000:
            raise DoubaoVoiceError("tts_text_size")
        session = DuplexSession(self.options, kind="tts")
        self._sessions.add(session)
        try:
            await session.start()
            await session.send("input_audio_mute.commit")
            # 独立单句使用官方SayHello；replacement是已有响应的流式干预事件。
            await session.send("speech_text_buffer.commit", text=text)
            response = None
            started = False
            total = 0
            for _ in range(10000):
                event = await session.receive()
                kind = event["type"]
                if kind in ("response.output_audio.started", "response.output_audio.delta", "response.output_audio.done"):
                    identifier = event.get("response_id") or None
                    if identifier is not None:
                        if not isinstance(identifier, str) or response is not None and identifier != response:
                            raise DoubaoVoiceError("speech_mismatch")
                        response = identifier
                if kind == "response.output_audio.started":
                    if event.get("tts_type") != "chat_tts_text":
                        raise DoubaoVoiceError("unexpected_speech")
                    started = True
                elif kind in ("response.output_audio.delta", "response.output_audio.done"):
                    # 服务可能省略分片response_id；独立连接仅发送一个指定文本，仍必须先有start。
                    if not started:
                        raise DoubaoVoiceError("speech_mismatch")
                    if kind.endswith(".done"):
                        if event.get("status_code", 0) not in (0, 200, 20000000) or not total:
                            raise DoubaoVoiceError("tts_incomplete")
                        session.record("completed")
                        return
                    try:
                        chunk = base64.b64decode(event["delta"], validate=True)
                    except (KeyError, ValueError, TypeError):
                        raise DoubaoVoiceError("audio_encoding") from None
                    total += len(chunk)
                    if not chunk or len(chunk) % 2 or total > self.sample_rate * 2 * self.options.session_seconds:
                        raise DoubaoVoiceError("output_format_or_limit")
                    yield chunk
            raise DoubaoVoiceError("event_limit")
        finally:
            self._sessions.discard(session)
            await session.close()

    async def close(self):
        await asyncio.gather(*(session.close() for session in list(self._sessions)))
