"""语音识别（P1 步骤 1.3）。

接口按评审要求定义为 ``start / feed / finish / close`` 四段式，
并产出 ``partial`` / ``final`` 两类事件。

- ``DummyASR``：返回**预设转写**，仅用于协议与流程测试。
  评审明确：它不具备真实识别能力，不能用于任何质量结论。
- ``XfyunASR``：待联调骨架。启用前必须按供应商产品文档核对
  APP_ID / API_KEY / 签名密钥、音频规格、会话时长与结束帧语义。
  特别注意：**不得用"每 60 秒发空帧"替代会话生命周期设计**。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass(frozen=True)
class Transcript:
    """一次转写结果。``is_final`` 为真表示本段发言的最终文本。"""

    text: str
    is_final: bool


class ASRClient(Protocol):
    """一段用户发言对应一个识别会话。

    生命周期：``start()`` → 多次 ``feed()`` → ``finish()`` → ``close()``。
    连接断开或发言取消时必须调用 ``close()`` 释放远端会话（计费与配额）。
    """

    async def start(self) -> None: ...

    async def feed(self, pcm: bytes, *, sample_rate: int) -> list[Transcript]: ...

    async def finish(self) -> str: ...

    async def close(self) -> None: ...


class DummyASR:
    """协议测试替身：把注入的文本当作识别结果返回。

    行为约定：
    - ``feed`` 始终返回空列表（不伪造 partial，避免测试误判流式能力）；
    - ``finish`` 返回最后一次 ``inject`` 的文本，**且只返回一次**；
      第二次调用返回空串——对应"同一个 turn 的 final 只能提交一次"的约束。
    """

    def __init__(self, *, default_text: str = "") -> None:
        self._pending: list[str] = []
        self._fallback = default_text
        self._started = False
        self._consumed = False
        self._closed = False

    @property
    def consumed(self) -> bool:
        return self._consumed

    def inject(self, text: str) -> None:
        """排队一段待返回的转写（离线演示 / 冒烟脚本用）。"""
        self._pending.append(text)

    async def start(self) -> None:
        self._started = True
        self._consumed = False

    async def feed(self, pcm: bytes, *, sample_rate: int) -> list[Transcript]:
        return []

    async def finish(self) -> str:
        if self._consumed:
            return ""
        self._consumed = True
        if self._pending:
            return self._pending.pop(0)
        return self._fallback

    async def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


class XfyunASR:
    """讯飞流式识别骨架（待联调）。

    联调清单：
    1. 按选定产品核对凭据（APP_ID / API_KEY / 签名密钥）与鉴权方式；
    2. 确认音频规格（编码、采样率、位深、帧长）与本项目 16k/s16le/100ms 是否一致，
       不一致需在 ``feed`` 内转换；
    3. 实现会话生命周期（开始帧 / 音频帧 / 结束帧）与超时、重连、取消清理；
    4. partial 覆盖语义：后续 partial 会替换前文，上层需按此更新字幕；
    5. 与 ``evals/wer_eval.py`` 联调，报中文 CER 与技术术语错误率。
    """

    def __init__(self, *, app_id: str, api_key: str, secret_key: str) -> None:
        raise NotImplementedError(
            "XfyunASR 尚未联调：请先核对供应商凭据与音频规格"
            "（docs/技术实现步骤.md 步骤 1.3），当前请使用 VOICE_ASR_PROVIDER=dummy"
        )


async def collect_final(asr: ASRClient, chunks: AsyncIterator[bytes], *, sample_rate: int) -> str:
    """把一个音频帧流喂给识别会话并取回 final 文本（便于测试与离线脚本）。"""
    await asr.start()
    try:
        async for pcm in chunks:
            await asr.feed(pcm, sample_rate=sample_rate)
        return await asr.finish()
    finally:
        await asr.close()
