"""语音通道：音频帧 → 文本（P1 步骤 1.1 / 1.3）。

职责边界：只负责"上行音频流"这一侧——帧序校验、前置缓冲、VAD、
ASR 会话生命周期、final 单次提交。**不碰面试业务状态**，
产出的 final 文本交由 ``ws.py`` 走既有的 turn 提交链路。

评审要点落地（docs/技术实现步骤.md 步骤 1.3）：
- 维护前置音频缓冲，避免 VAD 确认前丢掉首字；
- 同一个 turn 的 final 只能提交一次；
- 序号缺口必须被记录并重置该流，**不可悄悄丢音频**；
- 发言超长要切段，不能让缓冲无界增长。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.voice import audio
from app.voice.asr import ASRClient, Transcript
from app.voice.vad import PrerollBuffer, VAD, VadState

logger = logging.getLogger(__name__)


@dataclass
class FrameResult:
    """单帧处理结果。"""

    events: list[dict] = field(default_factory=list)
    speech_started: bool = False     # 本轮发言首次被确认（上层据此触发打断）
    utterance_ended: bool = False
    error: str | None = None


@dataclass
class TurnBinding:
    turn_id: str
    expected_seq: int = 0
    gaps: int = 0
    received_frames: int = 0
    received_ms: float = 0.0


class VoiceChannel:
    """一次 WS 连接对应一个实例。"""

    def __init__(
        self,
        *,
        vad: VAD,
        asr: ASRClient,
        sample_rate: int = audio.SAMPLE_RATE,
        preroll_ms: float = 400.0,
        max_frame_bytes: int = audio.MAX_FRAME_BYTES,
        max_utterance_seconds: float = 120.0,
    ) -> None:
        if max_utterance_seconds <= 0:
            raise ValueError("max_utterance_seconds 必须为正数")
        self._vad = vad
        self._asr = asr
        self._sample_rate = sample_rate
        self._max_frame_bytes = max_frame_bytes
        self._max_utterance_ms = max_utterance_seconds * 1000.0
        self._preroll = PrerollBuffer(keep_ms=preroll_ms)
        self._binding: TurnBinding | None = None
        self._asr_open = False
        self._final_submitted = False
        self._sealed = False
        self._last_gap_detail: str | None = None
        self._t_vad_end: float | None = None
        self._total_ms = 0.0
        self._remote_final = False
        self._asr_failed = False

    # ------------------------------------------------------------ 只读状态

    @property
    def active(self) -> bool:
        """是否有正在进行的发言流。"""
        return self._binding is not None

    @property
    def turn_id(self) -> str | None:
        return self._binding.turn_id if self._binding else None

    @property
    def gaps(self) -> int:
        return self._binding.gaps if self._binding else 0

    @property
    def last_gap_detail(self) -> str | None:
        """最近一次序号缺口说明（供连接层记录日志）。"""
        return self._last_gap_detail

    @property
    def final_submitted(self) -> bool:
        return self._final_submitted

    # ------------------------------------------------------------ 帧输入

    async def feed(
        self, data: str, *, turn_id: str, seq: int
    ) -> FrameResult:
        """处理一个上行音频帧。"""
        if self._binding and self._binding.turn_id != turn_id:
            # 上一轮发言没结束就换了 turn：拒绝，要求客户端先发 audio_end。
            return FrameResult(error="上一段发言尚未结束，请先发送 audio_end")
        if self._sealed:
            # VAD 已判定结束（或超长强制收束），等待 finish()/audio_end。
            return FrameResult(error="本段发言已判定结束，请发送 audio_end 后开始下一段")

        try:
            pcm = audio.decode_frame(data, max_bytes=self._max_frame_bytes)
        except audio.AudioFormatError as exc:
            return FrameResult(error=f"音频帧非法：{exc}")

        if self._binding is None:
            # 新一段发言：绑定新 turn 并复位"已提交"标记。
            # （否则第二段发言的 final 会因为上一段的标记而永远提交不出去。）
            self._binding = TurnBinding(turn_id=turn_id)
            self._final_submitted = False
            self._sealed = False
        binding = self._binding

        gap_error: str | None = None
        if seq != binding.expected_seq:
            # 重复帧（seq 落后）直接丢弃并计数；缺口（seq 跳跃）需要重置该流，
            # 因为缺口后的音频与已有缓冲无法可靠拼接。
            binding.gaps += 1
            if seq < binding.expected_seq:
                logger.warning("voice: 重复帧 turn=%s seq=%s", turn_id, seq)
                return FrameResult(error="收到重复音频帧，已丢弃")
            logger.warning(
                "voice: 序号缺口 turn=%s expected=%s got=%s", turn_id, binding.expected_seq, seq
            )
            await self._reset_stream(keep_binding=True)
            gap_error = f"音频流序号缺口（{binding.expected_seq}→{seq}），已重置该段发言缓冲"

        binding.expected_seq = seq + 1
        binding.received_frames += 1

        span = audio.duration_ms(pcm, sample_rate=self._sample_rate)
        binding.received_ms += span
        self._total_ms += span

        state = self._vad.feed(pcm, sample_rate=self._sample_rate)
        events: list[dict] = []

        speech_started = False
        if self._vad.armed and not self._asr_open:
            # VAD 达到最短语音时长（armed）：开启识别会话，
            # 并把前置缓冲补进去，避免丢掉首字。
            await self._open_asr(turn_id)
            if self._asr_failed:
                events.append({"type": "voice_error", "turn_id": turn_id, "detail": "识别连接失败，请改用文字或重试"})
            speech_started = True
            for buffered in self._preroll.drain():
                await self._feed_asr(buffered, events)
            await self._feed_asr(pcm, events)
        elif self._asr_open:
            await self._feed_asr(pcm, events)
        else:
            # 尚未武装：帧先留在前置缓冲里（可能是首字，也可能是噪声）。
            self._preroll.push(pcm, sample_rate=self._sample_rate)

        if gap_error:
            # 缺口是**可恢复**的客户端差错，不用 error 字段（那会走通用错误通道），
            # 而是发一个语义明确的 voice_gap 事件，让前端可见、可落库统计。
            events.append({"type": "voice_gap", "turn_id": turn_id, "detail": gap_error})
            self._last_gap_detail = gap_error

        ended = state is VadState.UTTERANCE_END or self._remote_final or self._asr_failed
        if not ended and self._total_ms >= self._max_utterance_ms:
            # 超长发言：强制收束为一段（VAD 也会在 max_utterance_ms 处返回 END，
            # 这里是第二道保险，防止单帧极小导致 VAD 侧统计滞后）。
            logger.info("voice: 发言超长强制结束 turn=%s", turn_id)
            ended = True
        if ended:
            # 封闭该流：在 audio_end/finish 之前拒绝继续喂帧，
            # 避免尾帧被算进下一轮发言。
            self._sealed = True
            # 服务端单调时钟：VAD 判定点。与 tts_chunk 的 t_emit 同源，
            # 客户端据此可算出"VAD确认→首片下发"（同机时钟可相减；
            # 跨到浏览器则必须由前端另行打点，见 evals/latency_probe.py）。
            self._t_vad_end = time.monotonic()

        return FrameResult(events=events, speech_started=speech_started, utterance_ended=ended)

    async def finish(self) -> tuple[str | None, list[dict]]:
        """结束本轮发言并取回 final 文本。

        返回 ``(final_text, events)``；已提交过则返回 ``(None, [])``——
        对应"同一个 turn 的 final 只能提交一次"。
        """
        if self._final_submitted:
            return None, []
        if self._binding is None:
            return None, []

        events: list[dict] = []
        turn_id = self._binding.turn_id
        text = ""
        if self._asr_open:
            try:
                if not self._asr_failed:
                    text = (await self._asr.finish()).strip()
            except Exception as exc:  # 识别失败不能让连接挂掉
                logger.warning("voice: ASR finish 失败 turn=%s reason=%s", turn_id, type(exc).__name__)
                events.append({"type": "voice_error", "turn_id": turn_id, "detail": "识别服务异常，请重试或改用文字"})
            finally:
                await self._close_asr()
        self._final_submitted = True
        self._binding = None
        self._sealed = False
        # 先取出时间戳再清理状态：早先把置空写在构造事件之前，
        # 导致 t_vad_end 永远为 None（延迟探针因此拿不到服务端分段）。
        vad_end_stamp = self._t_vad_end
        self._t_vad_end = None
        self._vad.reset()
        self._preroll.clear()
        self._total_ms = 0.0
        self._remote_final = False
        self._asr_failed = False

        if not text:
            events.append({"type": "voice_empty", "turn_id": turn_id, "detail": "未识别到有效语音"})
            return None, events
        event: dict = {"type": "asr_final", "turn_id": turn_id, "text": text}
        if vad_end_stamp is not None:
            event["t_vad_end"] = vad_end_stamp
        events.append(event)
        return text, events

    # ------------------------------------------------------------ 取消与清理

    async def cancel(self, *, reason: str) -> list[dict]:
        """取消当前发言流（打断或断线）。返回需下发的事件。"""
        if self._binding is None:
            return []
        turn_id = self._binding.turn_id
        await self._reset_stream(keep_binding=False)
        logger.info("voice: 取消发言 turn=%s reason=%s", turn_id, reason)
        return [{"type": "voice_cancelled", "turn_id": turn_id, "reason": reason}]

    async def close(self) -> None:
        await self._reset_stream(keep_binding=False)

    # ------------------------------------------------------------ 内部

    async def _open_asr(self, turn_id: str) -> None:
        try:
            await self._asr.start()
            self._asr_open = True
        except Exception as exc:
            logger.warning("voice: ASR start 失败 turn=%s reason=%s", turn_id, type(exc).__name__)
            self._asr_open = False
            self._asr_failed = True

    async def _feed_asr(self, pcm: bytes, events: list[dict]) -> None:
        if not self._asr_open or self._asr_failed:
            return
        try:
            chunks: list[Transcript] = await self._asr.feed(pcm, sample_rate=self._sample_rate)
        except Exception as exc:
            logger.warning("voice: ASR feed 失败 reason=%s", type(exc).__name__)
            self._asr_failed = True
            events.append({"type": "voice_error", "turn_id": self.turn_id, "detail": "识别中断，本段未提交，请重试或改用文字"})
            return
        for chunk in chunks:
            # 远端判停也走finish单次提交，避免feed和finish各发一条final。
            if chunk.is_final:
                self._remote_final = True
                continue
            # partial 覆盖语义：后到的 partial 替换前文，前端按此渲染灰字。
            events.append(
                {
                    "type": "asr_partial" if not chunk.is_final else "asr_final",
                    "turn_id": self._binding.turn_id if self._binding else "",
                    "text": chunk.text,
                }
            )

    async def _close_asr(self) -> None:
        if not self._asr_open:
            return
        self._asr_open = False
        try:
            await self._asr.close()
        except Exception as exc:
            logger.debug("voice: ASR close 失败 reason=%s", type(exc).__name__)

    async def _reset_stream(self, *, keep_binding: bool) -> None:
        await self._close_asr()
        self._vad.reset()
        self._preroll.clear()
        self._total_ms = 0.0
        self._remote_final = False
        self._asr_failed = False
        if keep_binding and self._binding is not None:
            # 保留 turn 绑定与 seq 期望值，只清音频缓冲：缺口后的音频必须丢弃。
            self._binding.received_frames = 0
            self._binding.received_ms = 0.0
            self._sealed = False  # 缺口后允许在同一发言内重新开始识别
        else:
            self._binding = None
            self._sealed = False
