"""VAD 与语音通道测试（对应 docs/技术实现步骤.md 步骤 1.3 验收）。

覆盖：端点判定、最短语音门槛、前置缓冲防丢首字、序号缺口重置、
重复帧丢弃、换 turn 拒绝、final 单次提交、超长发言收束。

注意：EnergyVAD 是能量法替身，本文件验证的是**流程正确性**，
不是识别质量；端点误差与误切/漏检必须用录音标注另行评测（评审要求）。
"""
from __future__ import annotations

import asyncio
import base64

import pytest

from app.voice import audio
from app.voice.asr import DummyASR
from app.voice.channel import VoiceChannel
from app.voice.vad import EnergyVAD, PrerollBuffer, VadState

TURN = "b" * 32
OTHER_TURN = "c" * 32

SILENT = b"\x00\x00" * 1600
LOUD = (9000).to_bytes(2, "little", signed=True) * 1600


def b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode()


def make_channel(*, asr: DummyASR | None = None, **kwargs) -> tuple[VoiceChannel, DummyASR]:
    asr = asr or DummyASR()
    vad = EnergyVAD(
        rms_threshold=500.0, silence_ms=700.0, min_speech_ms=200.0,
        max_utterance_ms=kwargs.pop("max_utterance_ms", 120_000.0),
    )
    channel = VoiceChannel(vad=vad, asr=asr, **kwargs)
    return channel, asr


def run(coro):
    return asyncio.run(coro)


class TestEnergyVAD:
    def test_silence_stays_silent(self):
        vad = EnergyVAD()
        assert vad.feed(SILENT, sample_rate=16000) is VadState.SILENCE
        assert vad.armed is False

    def test_short_blip_does_not_arm(self):
        """100ms 毛刺小于 min_speech_ms(200ms) 的门槛：不应开启一轮发言。"""
        vad = EnergyVAD(min_speech_ms=200.0)
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.armed is False

    def test_speech_arms_then_ends_after_silence(self):
        vad = EnergyVAD(min_speech_ms=200.0, silence_ms=700.0)
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.armed is True
        # 700ms 静默需要 7 个 100ms 帧
        for _ in range(6):
            assert vad.feed(SILENT, sample_rate=16000) is VadState.SILENCE
        assert vad.feed(SILENT, sample_rate=16000) is VadState.UTTERANCE_END

    def test_reset_after_end(self):
        vad = EnergyVAD(min_speech_ms=200.0, silence_ms=700.0)
        vad.feed(LOUD, sample_rate=16000)
        vad.feed(LOUD, sample_rate=16000)
        for _ in range(7):
            state = vad.feed(SILENT, sample_rate=16000)
        assert state is VadState.UTTERANCE_END
        assert vad.armed is False
        assert vad.silence_run_ms == 0.0

    def test_speech_resets_silence_counter(self):
        """说话中夹杂短静默不应判定结束。"""
        vad = EnergyVAD(min_speech_ms=200.0, silence_ms=700.0)
        vad.feed(LOUD, sample_rate=16000)
        vad.feed(LOUD, sample_rate=16000)
        vad.feed(SILENT, sample_rate=16000)
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.silence_run_ms == 0.0

    def test_max_utterance_forces_end(self):
        vad = EnergyVAD(min_speech_ms=200.0, max_utterance_ms=300.0)
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.feed(LOUD, sample_rate=16000) is VadState.SPEECH
        assert vad.feed(LOUD, sample_rate=16000) is VadState.UTTERANCE_END

    def test_rejects_invalid_construction(self):
        with pytest.raises(ValueError):
            EnergyVAD(rms_threshold=-1)
        with pytest.raises(ValueError):
            EnergyVAD(silence_ms=0)


class TestPrerollBuffer:
    def test_keeps_recent_frames_only(self):
        buffer = PrerollBuffer(keep_ms=300.0)
        for _ in range(10):
            buffer.push(SILENT, sample_rate=16000)  # 每帧 100ms
        assert len(buffer) <= 4  # 保留 ~300ms，不含将要淘汰的头部帧

    def test_drain_returns_frames_and_clears(self):
        buffer = PrerollBuffer(keep_ms=400.0)
        buffer.push(SILENT, sample_rate=16000)
        buffer.push(SILENT, sample_rate=16000)
        frames = buffer.drain()
        assert len(frames) >= 1
        assert len(buffer) == 0

    def test_rejects_invalid_keep(self):
        with pytest.raises(ValueError):
            PrerollBuffer(keep_ms=0)


class TestVoiceChannelFrames:
    def test_invalid_base64_returns_error_not_exception(self):
        channel, _ = make_channel()
        result = run(channel.feed("!!not-base64!!", turn_id=TURN, seq=0))
        assert result.error is not None
        assert result.events == []

    def test_speech_start_feeds_preroll(self):
        """前置缓冲必须在 VAD 武装时补进 ASR（防丢首字）。"""
        channel, asr = make_channel()
        # 先 3 帧静音（进入前置缓冲），再两帧语音触发武装
        for seq in range(3):
            run(channel.feed(b64(SILENT), turn_id=TURN, seq=seq))
        result_a = run(channel.feed(b64(LOUD), turn_id=TURN, seq=3))
        result_b = run(channel.feed(b64(LOUD), turn_id=TURN, seq=4))
        assert result_a.speech_started is True or result_b.speech_started is True
        asr.inject("B+树是多路平衡搜索树")
        text, events = run(channel.finish())
        assert text == "B+树是多路平衡搜索树"
        assert any(e["type"] == "asr_final" for e in events)

    def test_duplicate_seq_is_dropped(self):
        channel, _ = make_channel()
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        result = run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        assert result.error is not None and "重复" in result.error

    def test_seq_gap_resets_stream_and_reports(self):
        """缺口必须被记录并重置该流，不能悄悄丢音频。

        缺口是可恢复的客户端差错 → 发 voice_gap 事件（而非走通用 error 通道），
        同时重置该段缓冲，避免把缺口两侧的音频拼在一起送识别。
        """
        channel, _ = make_channel()
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        result = run(channel.feed(b64(LOUD), turn_id=TURN, seq=5))
        gaps = [e for e in result.events if e["type"] == "voice_gap"]
        assert gaps and "缺口" in gaps[0]["detail"]
        assert channel.gaps == 1
        assert channel.last_gap_detail is not None
        assert result.error is None, "缺口不应走通用错误通道"

    def test_turn_switch_requires_end(self):
        channel, _ = make_channel()
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        result = run(channel.feed(b64(LOUD), turn_id=OTHER_TURN, seq=0))
        assert result.error is not None and "audio_end" in result.error

    def test_final_submitted_only_once(self):
        channel, _ = make_channel()
        asr = DummyASR()
        channel, _ = make_channel(asr=asr)
        asr.inject("第一次")
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=1))
        first, _ = run(channel.finish())
        second, events = run(channel.finish())
        assert first == "第一次"
        assert second is None and events == []

    def test_empty_speech_reports_voice_empty(self):
        channel, _ = make_channel()
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=1))
        text, events = run(channel.finish())
        assert text is None
        assert any(e["type"] == "voice_empty" for e in events)

    def test_finish_without_speech_is_noop(self):
        channel, _ = make_channel()
        assert run(channel.finish()) == (None, [])

    def test_cancel_clears_stream(self):
        channel, _ = make_channel()
        run(channel.feed(b64(LOUD), turn_id=TURN, seq=0))
        events = run(channel.cancel(reason="barge_in"))
        assert channel.active is False
        assert events and events[0]["type"] == "voice_cancelled"
        assert events[0]["reason"] == "barge_in"

    def test_cancel_without_stream_is_noop(self):
        channel, _ = make_channel()
        assert run(channel.cancel(reason="barge_in")) == []

    def test_oversize_frame_rejected_by_channel(self):
        channel, _ = make_channel(max_frame_bytes=3200)
        huge = b64(b"\x00\x00" * 2000)
        result = run(channel.feed(huge, turn_id=TURN, seq=0))
        assert result.error is not None
