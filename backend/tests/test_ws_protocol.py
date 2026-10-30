"""音频帧与协议测试（对应 docs/技术实现步骤.md 步骤 1.1 验收）。

覆盖：合法帧、超限、非法编码、样本未对齐；重复/缺失序号；旧 turn；
以及 AudioMessage 的 schema 约束。Dummy 只证明协议可用，不代表识别能力。
"""
from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.schemas import AudioEndMessage, AudioMessage, incoming_message
from app.voice import audio

TURN = "a" * 32


def frame_bytes(samples: int = 1600) -> bytes:
    return b"\x01\x02" * samples


def frame_b64(samples: int = 1600) -> str:
    return base64.b64encode(frame_bytes(samples)).decode()


class TestAudioCodec:
    def test_frame_size_matches_spec(self):
        """评审固定规格：1600 样本 = 3200 字节 = 4268 base64 字符。"""
        assert audio.SAMPLES_PER_FRAME == 1600
        assert audio.BYTES_PER_FRAME == 3200
        assert len(frame_b64()) == 4268
        assert audio.MAX_FRAME_BASE64_CHARS == 8536

    def test_decode_valid_frame(self):
        raw = audio.decode_frame(frame_b64())
        assert len(raw) == 3200
        assert audio.samples(raw) == 1600
        assert audio.duration_ms(raw) == 100.0

    def test_decode_rejects_bad_base64(self):
        with pytest.raises(audio.AudioFormatError):
            audio.decode_frame("not-base64!!")

    def test_decode_rejects_odd_length(self):
        odd = base64.b64encode(b"\x01\x02\x03").decode()
        with pytest.raises(audio.AudioFormatError, match="整数倍"):
            audio.decode_frame(odd)

    def test_decode_rejects_oversize(self):
        big = base64.b64encode(b"\x00\x00" * 4000).decode()
        with pytest.raises(audio.AudioFormatError, match="上限"):
            audio.decode_frame(big)

    def test_decode_rejects_empty(self):
        with pytest.raises(audio.AudioFormatError):
            audio.decode_frame("")

    def test_rms_separates_silence_from_speech(self):
        assert audio.rms(b"\x00\x00" * 1600) == 0.0
        loud = audio.rms((10000).to_bytes(2, "little", signed=True) * 1600)
        assert loud == pytest.approx(10000.0)

    def test_silence_generator_length(self):
        pcm = audio.silence_pcm(100, sample_rate=24000)
        assert audio.samples(pcm) == 2400
        assert audio.duration_ms(pcm, sample_rate=24000) == pytest.approx(100.0)


class TestAudioSchema:
    def test_valid_audio_message(self):
        message = incoming_message.validate_json(
            f'{{"type":"audio","turn_id":"{TURN}","seq":0,'
            f'"format":"pcm_s16le","sample_rate":16000,"channels":1,"data":"{frame_b64()}"}}'
        )
        assert isinstance(message, AudioMessage)
        assert message.seq == 0

    def test_rejects_non_16k_sample_rate(self):
        """服务端不做重采样，非 16k 输入必须被客户端转换后送达。"""
        with pytest.raises(ValidationError):
            incoming_message.validate_json(
                f'{{"type":"audio","turn_id":"{TURN}","seq":0,"sample_rate":48000,'
                f'"data":"{frame_b64()}"}}'
            )

    def test_rejects_oversize_data(self):
        with pytest.raises(ValidationError):
            incoming_message.validate_json(
                f'{{"type":"audio","turn_id":"{TURN}","seq":0,'
                f'"data":"{"A" * (audio.MAX_FRAME_BASE64_CHARS + 4)}"}}'
            )

    def test_rejects_bad_turn_id(self):
        with pytest.raises(ValidationError):
            incoming_message.validate_json(
                f'{{"type":"audio","turn_id":"t-1","seq":0,"data":"{frame_b64()}"}}'
            )

    def test_rejects_negative_or_missing_seq(self):
        for seq in ("-1", ""):
            with pytest.raises(ValidationError):
                incoming_message.validate_json(
                    f'{{"type":"audio","turn_id":"{TURN}","seq":{seq or "null"},'
                    f'"data":"{frame_b64()}"}}'
                )

    def test_rejects_extra_fields(self):
        """WSMessage 是 extra=forbid：拼错字段名必须报错而不是被忽略。"""
        with pytest.raises(ValidationError):
            incoming_message.validate_json(
                f'{{"type":"audio","turn_id":"{TURN}","seq":0,'
                f'"data":"{frame_b64()}","timestamp":123}}'
            )

    def test_audio_end_message(self):
        message = incoming_message.validate_json(
            f'{{"type":"audio_end","turn_id":"{TURN}"}}'
        )
        assert isinstance(message, AudioEndMessage)

    def test_interrupt_without_utterance_id_is_legal(self):
        """打断可能早于首个 tts_chunk 到达，utterance_id 必须可省略。"""
        message = incoming_message.validate_json('{"type":"interrupt"}')
        assert message.utterance_id is None

    def test_interrupt_with_utterance_id(self):
        message = incoming_message.validate_json('{"type":"interrupt","utterance_id":"u-17"}')
        assert message.utterance_id == "u-17"
