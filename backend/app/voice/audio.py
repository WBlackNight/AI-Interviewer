"""音频帧编解码与校验（P1 步骤 1.1/1.3）。

采集规格（经评审确认，见 docs/技术实现步骤.md 步骤 1.1）：
    16kHz / 单声道 / PCM signed-16 little-endian / 100ms 网络帧
    = 1600 样本 = 3200 字节 = base64 4268 字符（不含 JSON 外壳）

设计原则：所有解码入口都必须校验并**抛出明确异常**，不接受"宽容解析"——
音频流一旦静默损坏，表现为识别率下降而非报错，是最难排查的故障形态。
"""
from __future__ import annotations

import base64
import binascii
import struct

SAMPLE_RATE = 16_000
FRAME_MS = 100
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 1600
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2             # 3200
BYTES_PER_SAMPLE = 2

#: 单帧字节上限。100ms 帧为 3200 字节，留出余量到 200ms（6400），
#: 超过即视为客户端分帧错误或恶意载荷。
MAX_FRAME_BYTES = 6_400

#: base64 展开后的理论最大字符数（含 padding），用于 schema 层长度预校验。
MAX_FRAME_BASE64_CHARS = ((MAX_FRAME_BYTES + 2) // 3) * 4


class AudioFormatError(ValueError):
    """音频帧非法：base64 损坏、长度不是样本整数倍、超出帧上限等。"""


def decode_frame(data: str, *, max_bytes: int = MAX_FRAME_BYTES) -> bytes:
    """base64 → PCM 字节，并校验长度上限与样本对齐。

    注意：不校验采样率——采样率是帧头字段，由上层 schema 约束，
    这里只负责「字节层面的合法性」。
    """
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AudioFormatError("音频帧不是合法的 base64") from exc
    if not raw:
        raise AudioFormatError("音频帧为空")
    if len(raw) > max_bytes:
        raise AudioFormatError(f"音频帧超过上限 {max_bytes} 字节（实际 {len(raw)}）")
    if len(raw) % BYTES_PER_SAMPLE:
        raise AudioFormatError("音频帧长度不是 16-bit 样本的整数倍")
    return raw


def encode_frame(pcm: bytes) -> str:
    """PCM 字节 → base64（下发 tts_chunk 用）。"""
    return base64.b64encode(pcm).decode("ascii")


def samples(pcm: bytes) -> int:
    """帧内样本数（16-bit 单声道）。"""
    return len(pcm) // BYTES_PER_SAMPLE


def duration_ms(pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> float:
    """帧时长（毫秒）。帧并不强制等于 100ms——拼接与重采样都会有尾帧。"""
    if sample_rate <= 0:
        raise ValueError("sample_rate 必须为正数")
    return samples(pcm) / sample_rate * 1000.0


def rms(pcm: bytes) -> float:
    """归一化前的均方根能量（int16 量纲）。

    用整数平方和计算：帧长固定（1600 样本），不会溢出 Python int，
    且避免 float 累积误差导致同音频在不同帧长下判定不一致。
    """
    count = samples(pcm)
    if count == 0:
        return 0.0
    total = 0
    for (value,) in struct.iter_unpack("<h", pcm):
        total += value * value
    return (total / count) ** 0.5


def silence_pcm(duration_ms_value: int, *, sample_rate: int) -> bytes:
    """生成静音 PCM（DummyTTS 用，验证播放通路而不伪造音频内容）。"""
    if duration_ms_value <= 0:
        raise ValueError("静音时长必须为正数")
    count = int(sample_rate * duration_ms_value / 1000)
    return b"\x00\x00" * count


def frame_bounds(total_samples: int, *, frame_samples: int = SAMPLES_PER_FRAME) -> int:
    """给定总样本数需要切分成多少个网络帧（向上取整，用于时长上限校验）。"""
    if frame_samples <= 0:
        raise ValueError("frame_samples 必须为正数")
    return (total_samples + frame_samples - 1) // frame_samples
