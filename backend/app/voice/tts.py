"""语音合成（P1 步骤 1.4）。

协议约定（评审要求）：**TTS 采样率在协议中明示，不默认等于 ASR 采样率**。
本项目选用 24kHz / 单声道 / PCM s16le —— 第一版直接下发 PCM，
浏览器转 Float32 后写入有界播放缓冲。

为什么不发 MP3/Opus 分片：``decodeAudioData`` 要求**完整音频文件数据**，
把任意压缩流分片逐片喂给它不成立；若改用压缩流，必须引入 MSE/AudioWorklet
解码器并明确封装格式。PCM 的代价是带宽（24kHz 单声道约 48KB/s），
在局域网/演示环境可接受，且省掉了前端解码器这一整块复杂度。

评审明确：``DummyTTS`` 输出静音，**不算语音成功**，只能验证通路。
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from app.voice import audio

#: 下发 TTS 音频的规格（写入 tts_chunk 帧头，前端据此重采样播放）。
TTS_SAMPLE_RATE = 24_000
TTS_CHANNELS = 1
TTS_FORMAT = "pcm_s16le"

#: 单个 tts_chunk 的目标时长：过长会阻塞首包，过短会放大帧开销。
TTS_CHUNK_MS = 100


class TTSClient(Protocol):
    """把一句文本合成为 PCM 分片流。"""

    @property
    def sample_rate(self) -> int: ...

    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...

    async def close(self) -> None: ...


class DummyTTS:
    """静音合成替身：按文本长度产出等长静音 PCM。

    用途：验证「切句 → 分片 → 下行 → 前端播放缓冲」整条通路的时序与边界，
    以及打断时旧分片不再进入播放器。**不提供任何音质结论。**
    """

    def __init__(
        self,
        *,
        sample_rate: int = TTS_SAMPLE_RATE,
        ms_per_char: int = 60,
        chunk_ms: int = TTS_CHUNK_MS,
    ) -> None:
        if sample_rate <= 0 or ms_per_char <= 0 or chunk_ms <= 0:
            raise ValueError("TTS 参数必须为正数")
        self._sample_rate = sample_rate
        self._ms_per_char = ms_per_char
        self._chunk_ms = chunk_ms

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        total_ms = max(len(text.strip()), 1) * self._ms_per_char
        emitted = 0
        while emitted < total_ms:
            span = min(self._chunk_ms, total_ms - emitted)
            emitted += span
            yield audio.silence_pcm(span, sample_rate=self._sample_rate)

    async def close(self) -> None:
        return None


class EdgeTTSClient:
    """edge-tts 实现（可选依赖，免费服务）。

    评审约束：**未经稳定性与使用条件核验的免费服务不能视为生产保障**。
    因此该实现仅作为演示期备用，启用前需要：
    1. 安装可选依赖 ``pip install edge-tts``；
    2. 实测失败率与首包延迟，并把失败降级为可观察的文字回退；
    3. 明确其服务条款是否允许比赛/公开发布场景使用。

    实现注意：edge-tts 输出的是 mp3 分片流，与本项目 PCM 协议不一致，
    因此需要在此处完成解码转 PCM——这也是它尚未默认启用的原因之一。
    """

    def __init__(self, *, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        raise NotImplementedError(
            "EdgeTTSClient 尚未联调：需要在实现内完成 mp3→PCM 转换并实测稳定性"
            "（docs/技术实现步骤.md 步骤 1.4），当前请使用 VOICE_TTS_PROVIDER=dummy"
        )
