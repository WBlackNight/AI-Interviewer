"""语音活动检测（P1 步骤 1.3）。

两套实现，由工厂按配置选择：
- ``EnergyVAD``：零依赖的 RMS 能量法。确定性，用于协议/流程测试与离线演示。
- ``SileroVAD``：真实模型实现，**当前为待联调骨架**——必须按评审要求固定
  模型文件与校验值，且注意官方 16kHz 输入窗口是 **512 样本（32ms）**，
  100ms 的 1600 样本帧不能直接当作单个推理窗口。

重要（评审意见，docs/技术实现步骤.md 步骤 1.3）：
    静默阈值 700ms、语音概率 0.5 只是**实验起点**，必须用录音标注验证
    端点误差、误切与漏检，不得表述为"已实测够用"。
"""
from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Protocol

from app.voice import audio


class VadState(str, Enum):
    """单帧喂入后的判定结果。"""

    SILENCE = "silence"              # 当前无语音
    SPEECH = "speech"                # 当前有语音
    UTTERANCE_END = "utterance_end"  # 曾检测到语音，且静默已达阈值 → 本轮发言结束


class VAD(Protocol):
    def feed(self, pcm: bytes, *, sample_rate: int) -> VadState: ...

    def reset(self) -> None: ...

    @property
    def armed(self) -> bool:
        """本轮是否已确认为"用户真的在说话"。

        上层据此决定何时开启 ASR 会话：只能在 ``armed`` 为真时开，
        否则一次咳嗽就会建立一个识别会话。
        """
        ...


class EnergyVAD:
    """RMS 能量 + 静默时长判定。

    判定过程（按样本累计，不依赖"每帧恰好 100ms"）：
    1. 逐帧算 RMS，与阈值比较；
    2. 连续语音累计到 ``min_speech_ms`` 才"武装"本轮发言（滤掉咳嗽、键盘声）；
    3. 已武装后，静默累计到 ``silence_ms`` → 返回 ``UTTERANCE_END`` 并自动复位。

    ``min_speech_ms`` 默认 200ms，是"武装门槛"而非识别门槛——
    低于它的孤立噪声不会开启一轮发言，避免空调/敲键盘误触发。
    """

    def __init__(
        self,
        *,
        rms_threshold: float = 500.0,
        silence_ms: float = 700.0,
        min_speech_ms: float = 200.0,
        max_utterance_ms: float = 120_000.0,
    ) -> None:
        if rms_threshold < 0:
            raise ValueError("rms_threshold 不能为负")
        if silence_ms <= 0 or min_speech_ms < 0:
            raise ValueError("silence_ms 必须为正且 min_speech_ms 非负")
        self._threshold = rms_threshold
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._max_utterance_ms = max_utterance_ms
        self._speech_ms = 0.0
        self._silence_run_ms = 0.0
        self._armed = False

    # -- 只读状态，供可观测性与测试断言
    @property
    def armed(self) -> bool:
        """本轮是否已确认为"用户真的在说话"。"""
        return self._armed

    @property
    def silence_run_ms(self) -> float:
        return self._silence_run_ms

    def feed(self, pcm: bytes, *, sample_rate: int) -> VadState:
        span = audio.duration_ms(pcm, sample_rate=sample_rate)
        loud = audio.rms(pcm) >= self._threshold

        if loud:
            self._speech_ms += span
            self._silence_run_ms = 0.0
            # 达到最短语音时长才算进入本轮发言；此前是对噪声的观察期。
            if not self._armed and self._speech_ms >= self._min_speech_ms:
                self._armed = True
            if self._armed and self._speech_ms >= self._max_utterance_ms:
                # 超长发言强制收束：交给上层切段，避免无界缓冲。
                self.reset()
                return VadState.UTTERANCE_END
            return VadState.SPEECH

        if not self._armed:
            # 尚未武装时静默：重新累计语音观察窗（例如单帧毛刺后归于安静）。
            self._speech_ms = 0.0
            return VadState.SILENCE

        self._silence_run_ms += span
        if self._silence_run_ms >= self._silence_ms:
            self.reset()
            return VadState.UTTERANCE_END
        return VadState.SILENCE

    def reset(self) -> None:
        self._speech_ms = 0.0
        self._silence_run_ms = 0.0
        self._armed = False


class PrerollBuffer:
    """前置音频缓冲：防止 VAD 确认前丢掉首字（评审硬要求）。

    说话起始的辅音能量低，等 VAD 武装时首字可能已过去 100~300ms。
    这里始终保留最近一段音频，武装瞬间把它作为发言前导送入 ASR。
    """

    def __init__(self, *, keep_ms: float = 400.0) -> None:
        if keep_ms <= 0:
            raise ValueError("keep_ms 必须为正数")
        self._keep_ms = keep_ms
        self._frames: deque[bytes] = deque()
        self._held_ms = 0.0

    def __len__(self) -> int:
        return len(self._frames)

    def push(self, pcm: bytes, *, sample_rate: int) -> None:
        """持续缓存最新帧；超出保留窗口时从头部丢弃。"""
        span = audio.duration_ms(pcm, sample_rate=sample_rate)
        self._frames.append(pcm)
        self._held_ms += span
        while self._frames and self._held_ms - audio.duration_ms(
            self._frames[0], sample_rate=sample_rate
        ) >= self._keep_ms:
            self._held_ms -= audio.duration_ms(self._frames.popleft(), sample_rate=sample_rate)

    def drain(self) -> list[bytes]:
        """取出并清空缓冲（武装时调用一次）。"""
        frames = list(self._frames)
        self._frames.clear()
        self._held_ms = 0.0
        return frames

    def clear(self) -> None:
        self._frames.clear()
        self._held_ms = 0.0


class SileroVAD:
    """Silero VAD 接入骨架（待联调）。

    联调清单（评审要求，缺一项都不算完成）：
    1. 固定模型来源与 SHA256 校验值，随镜像预置并做**离线加载测试**；
    2. 内部按 512 样本（32ms @16kHz）重分窗，不能把 100ms 网络帧直接推理；
    3. 每个会话持有独立模型状态（隐状态不能跨会话共享）；
    4. 采样率非 16kHz 时先重采样——模型只接受 8k/16k。
    """

    WINDOW_SAMPLES = 512  # 官方 16kHz 推理窗口

    def __init__(self) -> None:
        raise NotImplementedError(
            "SileroVAD 尚未联调：请按 docs/技术实现步骤.md 步骤 1.3 的清单"
            "固定模型与校验值后再启用；当前请使用 VOICE_VAD_PROVIDER=energy"
        )
