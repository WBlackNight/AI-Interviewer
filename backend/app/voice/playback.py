"""播放控制器：可播报事件 → TTS 分片 → 有界队列（P1 步骤 1.4 / 1.5）。

评审要求的落地（docs/技术实现步骤.md 步骤 1.4、1.5）：
- 音频发送是**独立任务**，与接收、业务处理解耦；三者以有界队列与取消令牌协作；
- 每个 utterance 的 seq 独立递增；
- 慢网络**不能无界排队**：队列满时按超时放弃该 utterance，并给出可观察的文字回退；
- 取消后旧片段不再进入发送队列，**迟到分片直接丢弃**；
- 持久化"utterance 取消事件及原因"（由 ``on_record`` 回调交给上层落库）。

与面试业务状态完全分离：本控制器只知道"哪些音频在放、放没放完"。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Awaitable, Callable, Iterable

from app.voice import audio
from app.voice.tts import TTS_CHUNK_MS, TTS_CHANNELS, TTS_FORMAT, TTSClient
from app.voice.utterance import speakable_texts, split_sentences

logger = logging.getLogger(__name__)

#: 队列满时的等待上限：超过即认为客户端消费不过来，放弃本 utterance。
QUEUE_PUT_TIMEOUT_SECONDS = 5.0

SendEvent = Callable[[dict], Awaitable[None]]
RecordEvent = Callable[[dict], Awaitable[None]]


class CancelToken:
    """一次 utterance 的取消令牌。

    用标志位而非 ``Task.cancel()``：TTS 供应商调用多为同步/半异步，
    强杀会留下未关闭的连接；这里让生产者**主动在检查点退出**，
    并保证退出的分片不再入队。
    """

    __slots__ = ("_cancelled", "reason")

    def __init__(self) -> None:
        self._cancelled = False
        self.reason: str | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self, reason: str) -> None:
        self._cancelled = True
        self.reason = reason


class PlaybackController:
    def __init__(
        self,
        tts: TTSClient,
        *,
        send_event: SendEvent,
        queue_max: int = 256,
        on_record: RecordEvent | None = None,
        chunk_ms: int = TTS_CHUNK_MS,
        put_timeout: float = QUEUE_PUT_TIMEOUT_SECONDS,
    ) -> None:
        if queue_max <= 0:
            raise ValueError("queue_max 必须为正数")
        if put_timeout <= 0:
            raise ValueError("put_timeout 必须为正数")
        self._tts = tts
        self._send = send_event
        self._record = on_record
        self._put_timeout = put_timeout
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=queue_max)
        self._sender: asyncio.Task | None = None
        self._producer: asyncio.Task | None = None
        self._token: CancelToken | None = None
        self._current: str | None = None
        self._sample_rate = tts.sample_rate
        self._chunk_bytes = int(self._sample_rate * chunk_ms / 1000) * audio.BYTES_PER_SAMPLE
        self._dropped = 0
        self._cancelled_count = 0

    # ------------------------------------------------------------ 只读状态

    @property
    def current_utterance(self) -> str | None:
        return self._current

    @property
    def playing(self) -> bool:
        return self._current is not None

    @property
    def dropped_utterances(self) -> int:
        return self._dropped

    @property
    def cancelled_utterances(self) -> int:
        return self._cancelled_count

    @property
    def queued_chunks(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        if self._sender is None:
            self._sender = asyncio.create_task(self._send_loop(), name="voice-sender")

    async def close(self) -> None:
        await self.interrupt(reason="connection_closed")
        if self._sender is not None:
            try:
                self._queue.put_nowait(None)  # 毒丸：让发送任务退出
            except asyncio.QueueFull:
                self._sender.cancel()
            self._sender = None
        try:
            await self._tts.close()
        except Exception as exc:
            logger.debug("voice: TTS close 失败 reason=%s", type(exc).__name__)

    # ------------------------------------------------------------ 播放

    async def speak(self, events: Iterable[dict], *, turn_id: str) -> str | None:
        """把一批面试事件转成语音播放。返回 utterance_id；无可播内容返回 None。

        非阻塞：生产在独立任务中进行，接收循环可以继续处理 interrupt。
        """
        sentences: list[str] = []
        for text in speakable_texts(events):
            pieces, _ = split_sentences(text, flush=True)
            sentences.extend(pieces or [text])
        if not sentences:
            return None

        # 新一轮播报开始前，先取消上一轮残留（防止叠音）。
        await self.interrupt(reason="superseded")

        utterance_id = f"u-{uuid.uuid4().hex[:12]}"
        self._current = utterance_id
        self._token = CancelToken()
        await self.start()
        self._producer = asyncio.create_task(
            self._produce(utterance_id, sentences, self._token), name="voice-producer"
        )
        return utterance_id

    async def interrupt(self, *, reason: str) -> str | None:
        """取消当前播报。返回被取消的 utterance_id（无则 None）。"""
        token, utterance_id = self._token, self._current
        if utterance_id is None:
            return None
        self._token = None
        self._current = None
        if token is not None:
            token.cancel(reason)
        if self._producer is not None:
            self._producer.cancel()
            self._producer = None
        self._cancelled_count += 1
        self._discard_queued(utterance_id)
        if self._record is not None:
            await self._record(
                {"type": "utterance_cancelled", "utterance_id": utterance_id, "reason": reason}
            )
        return utterance_id

    async def drain(self) -> None:
        """等待队列排空（测试与冒烟脚本用）。"""
        await self._queue.join()
        if self._producer is not None:
            try:
                await self._producer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 生产任务失败不影响排空
                pass

    # ------------------------------------------------------------ 内部

    async def _produce(
        self, utterance_id: str, sentences: list[str], token: CancelToken
    ) -> None:
        seq = 0
        pending = b""
        try:
            for sentence in sentences:
                if token.cancelled:
                    break
                async for chunk in self._tts.synthesize(sentence):
                    if token.cancelled:
                        break
                    pending += chunk
                    while len(pending) >= self._chunk_bytes:
                        frame, pending = pending[: self._chunk_bytes], pending[self._chunk_bytes:]
                        if not await self._enqueue(utterance_id, seq, frame, token):
                            return
                        seq += 1
            if pending and not token.cancelled:
                if not await self._enqueue(utterance_id, seq, pending, token):
                    return
                seq += 1
            if not token.cancelled:
                await self._enqueue_control(
                    {"type": "tts_end", "utterance_id": utterance_id}, token
                )
        except asyncio.CancelledError:
            # 正常取消路径（interrupt 已负责队列清理与落库）。
            raise
        except Exception as exc:
            logger.warning("voice: 合成失败 utterance=%s reason=%s", utterance_id, type(exc).__name__)
            self._discard_queued(utterance_id)
            await self._send({"type": "tts_error", "utterance_id": utterance_id,
                              "detail": "语音播报失败，可继续阅读题目或使用文字回答。"})
            if self._record is not None:
                await self._record(
                    {
                        "type": "tts_failed",
                        "utterance_id": utterance_id,
                        "reason": type(exc).__name__,
                    }
                )
        finally:
            # 落尾：若本轮仍是当前 utterance，标记播放结束。
            if self._current == utterance_id and not token.cancelled:
                self._current = None
                self._token = None

    async def _enqueue(self, utterance_id: str, seq: int, pcm: bytes, token: CancelToken) -> bool:
        """入队一个 tts_chunk。返回 False 表示本轮已放弃。"""
        if token.cancelled:
            return False
        event = {
            "type": "tts_chunk",
            "utterance_id": utterance_id,
            "seq": seq,
            "format": TTS_FORMAT,
            "sample_rate": self._sample_rate,
            "channels": TTS_CHANNELS,
            "data": audio.encode_frame(pcm),
        }
        if seq == 0:
            # 服务端单调时钟：首个分片入队时刻。与 asr_final 的 t_vad_end 同源，
            # 据此可精确算出"VAD确认→首片下发"这一段（不含浏览器播放）。
            event["t_emit"] = time.monotonic()
        return await self._enqueue_control(event, token)

    async def _enqueue_control(self, event: dict, token: CancelToken) -> bool:
        try:
            await asyncio.wait_for(self._queue.put(event), self._put_timeout)
            return True
        except asyncio.TimeoutError:
            # 客户端消费不过来：放弃本轮，避免服务端内存无界增长。
            self._dropped += 1
            token.cancel("client_backpressure")
            logger.warning(
                "voice: 队列背压超时，放弃播报 utterance=%s queued=%d",
                event.get("utterance_id"),
                self._queue.qsize(),
            )
            if self._record is not None:
                await self._record(
                    {
                        "type": "utterance_dropped",
                        "utterance_id": event.get("utterance_id"),
                        "reason": "client_backpressure",
                    }
                )
            return False

    def _discard_queued(self, utterance_id: str) -> None:
        """丢弃队列中属于该 utterance 的分片（迟到包）。"""
        kept: list[dict | None] = []
        dropped = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None and item.get("utterance_id") == utterance_id:
                dropped += 1
                self._queue.task_done()
            else:
                kept.append(item)
                self._queue.task_done()
        for item in kept:
            try:
                self._queue.put_nowait(item)
            except asyncio.QueueFull:  # 极端情况下宁可丢新包，也不阻塞取消路径
                logger.warning("voice: 取消回填队列失败，丢弃 1 个待发事件")
        if dropped:
            logger.info("voice: 丢弃迟到分片 %d 个 utterance=%s", dropped, utterance_id)

    async def _send_loop(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self._send(item)
            except Exception as exc:  # 发送失败只记录，交由连接层关闭
                logger.info("voice: 发送失败 reason=%s", type(exc).__name__)
                return
            finally:
                self._queue.task_done()
