"""切句与文本流工具（P1 步骤 1.4）。

评审约束（docs/技术实现步骤.md 步骤 1.4）：
    当前 LLM 接口只返回完整字符串，``session`` 一次返回整批事件，**没有 token 流**。
    第一阶段直接把完整问题事件交给流式 TTS 是允许的；
    但不能因为"插了一个 TTS 类"就宣称实现了 LLM 首句即播放——
    那需要新增 streaming 接口与增量事件。

因此本模块把「文本来源」抽象成异步迭代器（``AsyncIterator[str]``）：
现在由完整事件切句后喂入（``texts_from_events``），
将来 LLM 支持 token 流时只需替换来源，切句与合成逻辑不动。
"""
from __future__ import annotations

from typing import AsyncIterator, Iterable

#: 只对这些事件做语音合成；score/state 等纯数据事件不播报。
SPEAKABLE_EVENT_TYPES = frozenset({"greeting", "question", "agent_message", "closing"})

#: 句末标点。中文标点为主，兼容半角与换行。
SENTENCE_ENDINGS = "。！？；!?;\n"

#: 单句长度上限：超过则按逗号/顿号找次级切点，再不行硬切。
#: 防止 LLM 输出一段无标点长文本时首包被无限推迟。
MAX_SENTENCE_CHARS = 60

#: 次级切点（短句优先在这些位置断开，读起来更自然）。
SECONDARY_BREAKS = "，,、）)】」"


def split_sentences(
    buffer: str, *, flush: bool, max_chars: int = MAX_SENTENCE_CHARS
) -> tuple[list[str], str]:
    """切出完整句子。

    返回 ``(完整句列表, 残余缓冲)``。
    ``flush=True`` 时把残余缓冲也作为最后一句产出（文本流结束时调用）。
    """
    if max_chars <= 0:
        raise ValueError("max_chars 必须为正数")

    sentences: list[str] = []
    rest = buffer
    while True:
        cut = _find_break(rest, max_chars=max_chars)
        if cut < 0:
            break
        piece = rest[: cut + 1].strip()
        if piece:
            sentences.append(piece)
        rest = rest[cut + 1 :]

    if flush:
        tail = rest.strip()
        if tail:
            sentences.append(tail)
        rest = ""
    return sentences, rest


def _find_break(text: str, *, max_chars: int) -> int:
    """在 text 中找切点下标；无可用切点返回 -1。"""
    for index, char in enumerate(text):
        if char in SENTENCE_ENDINGS:
            return index
    if len(text) >= max_chars:
        # 长句无句末标点：回退到次级断点，再不行硬切。
        window = text[:max_chars]
        for index in range(len(window) - 1, 0, -1):
            if window[index] in SECONDARY_BREAKS:
                return index
        return max_chars - 1
    return -1


def event_text(event: dict) -> str:
    """取出事件中需要播报的文本。

    注意字段差异：``greeting / agent_message / closing`` 用 ``text``，
    而 ``question`` 用 ``content``（见 ``agent/session.py`` 的事件构造）。
    早期只读 ``text`` 会让所有题目静音，因此这里统一归一化。
    """
    for key in ("text", "content"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def speakable_texts(events: Iterable[dict]) -> list[str]:
    """从一批面试事件中抽出需要播报的文本（保持事件顺序）。"""
    texts: list[str] = []
    for event in events:
        if event.get("type") not in SPEAKABLE_EVENT_TYPES:
            continue
        text = event_text(event)
        if text:
            texts.append(text)
    return texts


async def texts_from_events(events: Iterable[dict]) -> AsyncIterator[str]:
    """把完整事件转成"文本增量流"。

    当前实现按句产出，等价于"每句一个增量"——它能让 TTS 分片在句子边界
    自然对齐，但**不减少 LLM 首 token 等待**（那需要上游 streaming）。
    """
    for text in speakable_texts(events):
        sentences, _ = split_sentences(text, flush=True)
        for sentence in sentences or [text]:
            yield sentence
