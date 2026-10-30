"""打断、切句与播放队列测试（对应 docs/技术实现步骤.md 步骤 1.4/1.5 验收）。

覆盖：切句边界、每 utterance 独立 seq、取消后旧分片不入队、
迟到分片丢弃、队列背压时放弃播报并落库原因。

注意：本文件验证的是**控制流**。真实打断延迟（用户开口→本地静音 P95<300ms）
依赖浏览器 10~20ms 独立检测窗，属于前端实测范围，不能用这里的用例代替。
"""
from __future__ import annotations

import asyncio

import pytest

from app.voice.playback import PlaybackController
from app.voice.tts import DummyTTS
from app.voice.utterance import split_sentences, speakable_texts, texts_from_events


def run(coro):
    return asyncio.run(coro)


class TestSplitSentences:
    def test_splits_on_chinese_endings(self):
        sentences, rest = split_sentences("你好。这是什么？好的！", flush=False)
        assert sentences == ["你好。", "这是什么？", "好的！"]
        assert rest == ""

    def test_keeps_incomplete_tail(self):
        sentences, rest = split_sentences("你好。还没说完", flush=False)
        assert sentences == ["你好。"]
        assert rest == "还没说完"

    def test_flush_emits_tail(self):
        sentences, rest = split_sentences("还没说完", flush=True)
        assert sentences == ["还没说完"]
        assert rest == ""

    def test_long_text_without_punctuation_is_cut(self):
        """LLM 输出无标点长文本时首包不能被无限推迟。"""
        sentences, rest = split_sentences("字" * 200, flush=False, max_chars=60)
        assert sentences, "长文本必须被强制切开"
        assert all(len(s) <= 61 for s in sentences)

    def test_prefers_secondary_break(self):
        text = "这是前半句，" + "字" * 60
        sentences, _ = split_sentences(text, flush=False, max_chars=60)
        assert sentences and sentences[0].endswith("，")

    def test_rejects_invalid_max_chars(self):
        with pytest.raises(ValueError):
            split_sentences("abc", flush=False, max_chars=0)


class TestSpeakableTexts:
    def test_only_speakable_types(self):
        events = [
            {"type": "state", "state": "questioning"},
            {"type": "greeting", "text": "你好"},
            {"type": "score", "score": 6.5},
            {"type": "question", "text": "讲讲索引"},
            {"type": "closing", "text": "再见"},
        ]
        assert speakable_texts(events) == ["你好", "讲讲索引", "再见"]

    def test_blank_text_ignored(self):
        assert speakable_texts([{"type": "greeting", "text": "   "}]) == []

    def test_texts_from_events_splits_sentences(self):
        async def scenario() -> list[str]:
            events = [{"type": "greeting", "text": "你好。我是面试官。"}]
            return [chunk async for chunk in texts_from_events(events)]

        assert run(scenario()) == ["你好。", "我是面试官。"]


class _Collector:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)

    def of(self, utterance_id: str) -> list[dict]:
        return [e for e in self.events if e.get("utterance_id") == utterance_id]


class TestPlaybackController:
    def test_speak_emits_chunks_then_end(self):
        async def scenario():
            collector, records = _Collector(), _Collector()
            controller = PlaybackController(
                DummyTTS(), send_event=collector, on_record=records, chunk_ms=100
            )
            utterance_id = await controller.speak(
                [{"type": "greeting", "text": "你好。我是面试官。"}], turn_id="t" * 32
            )
            assert utterance_id is not None
            await asyncio.wait_for(controller.drain(), timeout=5)
            await controller.close()
            return utterance_id, collector.of(utterance_id)

        utterance_id, events = run(scenario())
        chunks = [e for e in events if e["type"] == "tts_chunk"]
        assert chunks, "应产生 tts_chunk"
        assert events[-1]["type"] == "tts_end"
        # 每 utterance 独立 seq，从 0 连续递增
        assert [c["seq"] for c in chunks] == list(range(len(chunks)))
        # 帧头必须明示音频规格（不默认等于 ASR 采样率）
        assert chunks[0]["sample_rate"] == DummyTTS().sample_rate
        assert chunks[0]["format"] == "pcm_s16le"
        assert chunks[0]["channels"] == 1

    def test_chunk_payload_is_aligned_pcm(self):
        async def scenario():
            collector = _Collector()
            controller = PlaybackController(DummyTTS(), send_event=collector, chunk_ms=100)
            utterance_id = await controller.speak(
                [{"type": "closing", "text": "再见"}], turn_id="t" * 32
            )
            await asyncio.wait_for(controller.drain(), timeout=5)
            await controller.close()
            return collector.of(utterance_id)

        import base64
        from app.voice import audio

        for event in [e for e in run(scenario()) if e["type"] == "tts_chunk"]:
            pcm = base64.b64decode(event["data"])
            assert len(pcm) % audio.BYTES_PER_SAMPLE == 0

    def test_no_speakable_text_returns_none(self):
        async def scenario():
            controller = PlaybackController(DummyTTS(), send_event=_Collector())
            return await controller.speak([{"type": "score", "score": 1.0}], turn_id="t" * 32)

        assert run(scenario()) is None

    def test_interrupt_cancels_and_records(self):
        async def scenario():
            collector, records = _Collector(), _Collector()
            controller = PlaybackController(
                DummyTTS(), send_event=collector, on_record=records, chunk_ms=100
            )
            utterance_id = await controller.speak(
                [{"type": "question", "text": "请详细讲讲索引结构在项目中的应用。"}],
                turn_id="t" * 32,
            )
            cancelled = await controller.interrupt(reason="barge_in")
            await controller.close()
            return utterance_id, cancelled, records, controller

        utterance_id, cancelled, records, controller = run(scenario())
        assert cancelled == utterance_id
        assert any(e["type"] == "utterance_cancelled" and e["reason"] == "barge_in"
                   for e in records.events)
        assert controller.playing is False
        assert controller.cancelled_utterances == 1

    def test_late_chunks_are_not_enqueued_after_cancel(self):
        """取消后生产者必须停止：队列中不再为该 utterance 新增分片。

        边界说明：已经写入 socket 的在途帧无法召回——那是分布式语义的固有限制，
        由前端在收到 barge_in_ack 时清空播放缓冲来处理（见步骤 1.5 的设计约定）。
        本用例只断言服务端可保证的部分。
        """
        async def scenario():
            gate = asyncio.Event()

            async def blocking_send(event: dict) -> None:
                await gate.wait()

            controller = PlaybackController(
                DummyTTS(), send_event=blocking_send, chunk_ms=100, queue_max=64
            )
            utterance_id = await controller.speak(
                [{"type": "question", "text": "这是一个很长的题目。" * 20}],
                turn_id="t" * 32,
            )
            await asyncio.sleep(0.05)
            assert controller.queued_chunks > 0, "需要先制造队列积压"
            await controller.interrupt(reason="barge_in")
            remaining = [
                controller._queue.get_nowait()  # noqa: SLF001 - 断言队列内部状态
                for _ in range(controller.queued_chunks)
            ]
            gate.set()
            await asyncio.sleep(0.05)
            after = controller.queued_chunks
            await controller.close()
            return utterance_id, remaining, after, controller

        utterance_id, remaining, after, controller = run(scenario())
        assert not [e for e in remaining if e and e.get("utterance_id") == utterance_id]
        assert after == 0, "取消后不应再有新分片入队"
        assert controller.playing is False

    def test_discard_removes_queued_chunks_of_cancelled_utterance(self):
        """队列中尚未发出的旧分片必须被丢弃（迟到包）。"""
        async def scenario():
            gate = asyncio.Event()

            async def blocking_send(event: dict) -> None:
                await gate.wait()

            controller = PlaybackController(
                DummyTTS(), send_event=blocking_send, chunk_ms=100, queue_max=64
            )
            utterance_id = await controller.speak(
                [{"type": "question", "text": "很长的题目。" * 40}], turn_id="t" * 32
            )
            await asyncio.sleep(0.05)
            queued_before = controller.queued_chunks
            await controller.interrupt(reason="barge_in")
            remaining = [
                controller._queue.get_nowait()  # noqa: SLF001 - 断言队列内部状态
                for _ in range(controller.queued_chunks)
            ]
            gate.set()
            await controller.close()
            return utterance_id, queued_before, remaining

        utterance_id, queued_before, remaining = run(scenario())
        assert queued_before > 0, "需要先制造队列积压才能验证丢弃"
        assert not [e for e in remaining if e and e.get("utterance_id") == utterance_id]

    def test_backpressure_drops_utterance_on_slow_client(self):
        """慢客户端：发送阻塞导致队列填满 → 按超时放弃，不无限等待也不无限占内存。

        用阻塞的 send 模拟"客户端消费不过来"（真实场景：网络拥塞、
        浏览器标签页被挂起）。``speak`` 会自行启动发送任务，因此这里必须
        让发送真的卡住，才能形成背压。
        """
        async def scenario():
            gate = asyncio.Event()
            records = _Collector()

            async def stuck_send(event: dict) -> None:
                await gate.wait()

            controller = PlaybackController(
                DummyTTS(),
                send_event=stuck_send,
                on_record=records,
                chunk_ms=100,
                queue_max=2,
                put_timeout=0.05,
            )
            utterance_id = await controller.speak(
                [{"type": "question", "text": "很长的题目。" * 30}], turn_id="t" * 32
            )
            assert controller._producer is not None  # noqa: SLF001
            await asyncio.wait_for(asyncio.shield(controller._producer), timeout=5)  # noqa: SLF001
            gate.set()
            await controller.close()
            return utterance_id, records, controller

        utterance_id, records, controller = run(scenario())
        assert controller.dropped_utterances == 1
        assert any(
            e["type"] == "utterance_dropped" and e["utterance_id"] == utterance_id
            for e in records.events
        )

    def test_new_speak_supersedes_previous(self):
        """同一连接连续播报：新一轮开始前先取消上一轮，避免叠音。"""
        async def scenario():
            collector, records = _Collector(), _Collector()
            controller = PlaybackController(
                DummyTTS(), send_event=collector, on_record=records, chunk_ms=100
            )
            first = await controller.speak(
                [{"type": "greeting", "text": "第一句。" * 5}], turn_id="t" * 32
            )
            second = await controller.speak(
                [{"type": "question", "text": "第二句。"}], turn_id="t" * 32
            )
            await asyncio.wait_for(controller.drain(), timeout=5)
            await controller.close()
            return first, second, records

        first, second, records = run(scenario())
        assert first != second
        assert any(
            e["type"] == "utterance_cancelled" and e["reason"] == "superseded"
            for e in records.events
        )

    def test_rejects_invalid_construction(self):
        with pytest.raises(ValueError):
            PlaybackController(DummyTTS(), send_event=_Collector(), queue_max=0)
        with pytest.raises(ValueError):
            PlaybackController(DummyTTS(), send_event=_Collector(), put_timeout=0)
