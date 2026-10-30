"""语音链路端到端集成测试（P1 步骤 1.6 的可自动化部分）。

用 TestClient 走真实 WS：音频帧 → VAD 判定 → ASR(final) → 复用既有 turn 提交
→ 事件下发 → TTS 分片。ASR 用 DummyASR 注入预设文本（协议与流程验证，
不代表识别质量——评审明确要求，真实质量需 `evals/wer_eval.py` 另测）。

同时验证：语音未启用时拒绝音频帧、interrupt 保持文字模式提示、
语音启用时 interrupt 返回 barge_in_ack。
"""
from __future__ import annotations

import base64
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import get_db
from app.voice.asr import DummyASR
from app.voice.channel import VoiceChannel
from app.voice.vad import EnergyVAD

LOUD = (9000).to_bytes(2, "little", signed=True) * 1600
SILENT = b"\x00\x00" * 1600


def b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode()


def _make_client(monkeypatch, *, voice_enabled: bool, database_path=None):
    from app import main
    from app.api import ws, routes

    # 播报日志和评分会并发写入；文件数据库为线程提供独立连接，避免
    # StaticPool单连接上的一个Session回滚另一个Session尚未完成的事务。
    engine = create_engine(
        'sqlite:///' + database_path.as_posix() if database_path else 'sqlite://',
        connect_args={"check_same_thread": False},
        **({} if database_path else {'poolclass': StaticPool}),
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    config = Settings(
        _env_file=None, llm_api_key=None, judge0_url=None, voice_enabled=voice_enabled
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(ws, "SessionLocal", factory)
    monkeypatch.setattr(ws, "settings", config)
    monkeypatch.setattr(routes, "settings", config)

    asr = DummyASR()

    def channel_factory(_settings):
        return VoiceChannel(
            vad=EnergyVAD(rms_threshold=500.0, silence_ms=700.0, min_speech_ms=200.0),
            asr=asr,
            preroll_ms=400.0,
        )

    monkeypatch.setattr(ws, "build_voice_channel", channel_factory)
    app = main.create_app()

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    return TestClient(app), factory, asr, engine


@pytest.fixture
def voice_api(monkeypatch,tmp_path):
    client, factory, asr, engine = _make_client(monkeypatch, voice_enabled=True,database_path=tmp_path/'voice.sqlite3')
    with client:
        yield client, factory, asr
    engine.dispose()


@pytest.fixture
def text_api(monkeypatch,tmp_path):
    client, factory, asr, engine = _make_client(monkeypatch, voice_enabled=False,database_path=tmp_path/'text.sqlite3')
    with client:
        yield client, factory, asr
    engine.dispose()


def create_interview(client) -> dict:
    response = client.post("/api/interview", json={"position": "java_backend", "difficulty": "mid"})
    assert response.status_code == 200, response.text
    return response.json()


def open_session(client, interview):
    socket = client.websocket_connect(
        "/ws/interview/" + interview["interview_id"],
        subprotocols=["interview", interview["access_token"]],
    ).__enter__()
    socket.send_json({"type": "start"})
    snapshot = socket.receive_json()
    assert snapshot["type"] == "snapshot", snapshot
    return socket, snapshot


def send_audio(socket, turn_id: str, frames: list[bytes], *, start_seq: int = 0) -> int:
    seq = start_seq
    for pcm in frames:
        socket.send_json({"type": "audio", "turn_id": turn_id, "seq": seq, "data": b64(pcm)})
        seq += 1
    return seq


def collect(socket, *, until: set[str], limit: int = 80) -> list[dict]:
    events: list[dict] = []
    for _ in range(limit):
        event = socket.receive_json()
        events.append(event)
        if event["type"] in until:
            return events
    raise AssertionError(f"未在 {limit} 个事件内收到 {until}：{[e['type'] for e in events]}")


class TestVoiceTurnEndToEnd:
    def test_vad_tail_frames_do_not_open_another_utterance(self, voice_api):
        """VAD通知往返期间已排队的同段尾帧不能触发缺口、重复提交或打断评分。"""
        client, _factory, asr = voice_api
        asr.inject('第一次回答')
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn = snapshot['current_question']['turn_id']
        try:
            send_audio(socket, turn, [LOUD, LOUD] + [SILENT] * 7 + [LOUD] * 15)
            first = collect(socket, until={'tts_end','error'})
            assert not any(e['type'] in ('error','voice_gap') for e in first), first
            assert sum(e['type']=='voice_processing' for e in first)==1
            assert sum(e['type']=='answer_ack' for e in first)==1
            new_turn = next(e['turn_id'] for e in first if e['type']=='question')
            asr.inject('下一题继续回答')
            send_audio(socket, new_turn, [LOUD, LOUD] + [SILENT] * 7)
            second = collect(socket, until={'tts_end','error'})
            assert not any(e['type'] in ('error','voice_gap') for e in second), second
            assert sum(e['type']=='answer_ack' for e in second)==1
        finally:
            socket.close()

    def test_audio_frames_produce_transcript_turn_and_tts(self, voice_api):
        """[loud×2 触发武装] + [silent×7 触发 VAD 结束] → final → 轮次 → TTS。"""
        client, _factory, asr = voice_api
        asr.inject("B+树是多路平衡搜索树，叶子节点有链表，支持范围查询。")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]

        try:
            send_audio(socket, turn_id, [LOUD, LOUD] + [SILENT] * 7)
            events = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()

        kinds = [e["type"] for e in events]
        assert "error" not in kinds, events
        assert "asr_final" in kinds, kinds
        assert events[kinds.index("asr_final")]["text"].startswith("B+树"), events
        # 语音轮次复用了文字模式的事件流
        assert "answer_ack" in kinds and "score" in kinds, kinds
        # 语音模式下必须产生 TTS 分片
        chunks = [e for e in events if e["type"] == "tts_chunk"]
        assert chunks, kinds
        assert kinds[-1] == "tts_end", kinds
        # 帧头必须明示音频规格
        assert chunks[0]["sample_rate"] > 0 and chunks[0]["format"] == "pcm_s16le"
        assert chunks[0]["channels"] == 1
        # 每个 utterance 的 seq 从 0 连续递增
        assert [c["seq"] for c in chunks] == list(range(len(chunks)))

    def test_preroll_prevents_losing_first_syllable(self, voice_api):
        """前置缓冲：武装前送入的语音帧也必须进入识别输入。

        这里用"1 帧静音 + 2 帧语音"验证武装时会把缓冲补进 ASR——
        DummyASR 无法反映内容，但可以通过 final 仍被产出证明链路未断。
        """
        client, _factory, asr = voice_api
        asr.inject("第一个字不能丢")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            send_audio(socket, turn_id, [SILENT, LOUD, LOUD] + [SILENT] * 7)
            events = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()
        kinds = [e["type"] for e in events]
        assert "asr_final" in kinds and "error" not in kinds, events

    def test_second_utterance_can_submit_again(self, voice_api):
        """连续两段发言都必须能提交（回归：final 单次提交标记必须复位）。"""
        client, _factory, asr = voice_api
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            asr.inject("第一次回答")
            send_audio(socket, turn_id, [LOUD, LOUD] + [SILENT] * 7)
            # 等到第一轮播报结束，否则第二轮会先收到第一轮的 TTS 尾巴
            first = collect(socket, until={"tts_end", "error"})
            assert "error" not in [e["type"] for e in first], first
            assert "asr_final" in [e["type"] for e in first], first

            # 第二段发言：使用新题目下发的 turn 绑定，seq 从 0 重新开始
            new_turn = next(
                (e["turn_id"] for e in reversed(first) if e["type"] == "question"), None
            ) or turn_id
            asr.inject("第二次回答")
            send_audio(socket, new_turn, [LOUD, LOUD] + [SILENT] * 7, start_seq=0)
            second = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()
        kinds = [e["type"] for e in second]
        assert "error" not in kinds, second
        assert "asr_final" in kinds, kinds
        # 第二段发言的识别文本必须是新注入的那句（证明标记已复位、流已重建）
        final = next(e for e in second if e["type"] == "asr_final")
        assert final["text"] == "第二次回答", second

    def test_seq_gap_is_reported_not_silently_dropped(self, voice_api):
        client, _factory, asr = voice_api
        asr.inject("缺口后的内容")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            send_audio(socket, turn_id, [LOUD], start_seq=0)
            send_audio(socket, turn_id, [LOUD], start_seq=5)  # 跳号
            events = collect(socket, until={"voice_gap"})
        finally:
            socket.close()
        gap = next(e for e in events if e["type"] == "voice_gap")
        assert "缺口" in gap["detail"]

    def test_invalid_audio_frame_rejected(self, voice_api):
        client, _factory, _asr = voice_api
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            socket.send_json(
                {"type": "audio", "turn_id": turn_id, "seq": 0, "data": "!!!not-base64!!!"}
            )
            event = socket.receive_json()
        finally:
            socket.close()
        assert event["type"] == "error" and event["code"] == "voice_invalid"

    def test_audio_end_submits_without_vad(self, voice_api):
        """客户端主动 audio_end（按住说话/松开）也要能提交。"""
        client, _factory, asr = voice_api
        asr.inject("按键结束的发言")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            send_audio(socket, turn_id, [LOUD, LOUD])
            socket.send_json({"type": "audio_end", "turn_id": turn_id})
            events = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()
        kinds = [e["type"] for e in events]
        assert "asr_final" in kinds and "error" not in kinds, events


class TestVoiceDisabledAndInterrupt:
    def test_audio_rejected_when_voice_disabled(self, text_api):
        client, _factory, _asr = text_api
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            socket.send_json(
                {"type": "audio", "turn_id": turn_id, "seq": 0, "data": b64(LOUD)}
            )
            event = socket.receive_json()
        finally:
            socket.close()
        assert event["type"] == "error" and event["code"] == "voice_disabled"

    def test_interrupt_keeps_text_mode_message_when_voice_disabled(self, text_api):
        """行为兼容：语音关闭时 interrupt 仍是既有提示语。"""
        client, _factory, _asr = text_api
        interview = create_interview(client)
        socket, _snapshot = open_session(client, interview)
        try:
            socket.send_json({"type": "interrupt"})
            event = socket.receive_json()
        finally:
            socket.close()
        assert event["type"] == "agent_message" and "文字模式" in event["text"]

    def test_interrupt_returns_barge_in_ack_when_voice_enabled(self, voice_api):
        client, _factory, _asr = voice_api
        interview = create_interview(client)
        socket, _snapshot = open_session(client, interview)
        try:
            socket.send_json({"type": "interrupt"})
            event = socket.receive_json()
        finally:
            socket.close()
        assert event["type"] == "barge_in_ack"
        assert event["utterance_id"] is None, "没有播放中的语音时应明确说明"

    def test_voice_records_are_persisted(self, voice_api):
        """打断产生的取消事件必须落库（评审要求）。"""
        client, factory, _asr = voice_api
        interview = create_interview(client)
        socket, _snapshot = open_session(client, interview)
        try:
            socket.send_json({"type": "interrupt"})
            socket.receive_json()
        finally:
            socket.close()
        from sqlalchemy import select

        from app.models.entities import InterviewEvent

        with factory() as db:
            rows = list(
                db.scalars(
                    select(InterviewEvent).where(
                        InterviewEvent.interview_id == interview["interview_id"]
                    )
                )
            )
        assert rows, "事件流不应为空"


class TestVoiceTimestamps:
    """服务端单调时钟戳：延迟探针的"VAD确认→首片下发"依赖它们。

    这里守的是两个真实修过的顺序缺陷：
    - 时间戳在构造事件**之前**被置空 → 字段缺失；
    - 两个戳若倒置，同源相减会得到负延迟。
    """

    def test_asr_final_and_first_chunk_carry_server_stamps(self, voice_api):
        client, _factory, asr = voice_api
        asr.inject("带时间戳的回答")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            send_audio(socket, turn_id, [LOUD, LOUD] + [SILENT] * 7)
            events = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()

        final = next(e for e in events if e["type"] == "asr_final")
        assert "t_vad_end" in final, "asr_final 必须带服务端 VAD 判定时间戳"
        assert isinstance(final["t_vad_end"], float)

        chunks = [e for e in events if e["type"] == "tts_chunk"]
        assert chunks and "t_emit" in chunks[0], "首个 tts_chunk 必须带服务端入队时间戳"
        # 同源单调时钟：先 VAD 判定、后分片入队，顺序不可倒置
        assert chunks[0]["t_emit"] >= final["t_vad_end"]

    def test_only_first_chunk_carries_emit_stamp(self, voice_api):
        """只有 seq=0 带戳：避免每片都塞时间戳徒增协议负担。"""
        client, _factory, asr = voice_api
        asr.inject("多句回答。第二句在这里。")
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn_id = snapshot["current_question"]["turn_id"]
        try:
            send_audio(socket, turn_id, [LOUD, LOUD] + [SILENT] * 7)
            events = collect(socket, until={"tts_end", "error"})
        finally:
            socket.close()
        chunks = [e for e in events if e["type"] == "tts_chunk"]
        assert len(chunks) > 1
        assert "t_emit" in chunks[0]
        assert all("t_emit" not in c for c in chunks[1:])


class TestTurnSerialization:
    def test_text_answer_still_works_with_voice_enabled(self, voice_api):
        """语音开启不能破坏文字模式：answer 仍能正常推进。"""
        client, _factory, _asr = voice_api
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        try:
            socket.send_json(
                {
                    "type": "answer",
                    "message_id": uuid.uuid4().hex,
                    "turn_id": snapshot["current_question"]["turn_id"],
                    "version": snapshot["version"],
                    "text": "B+树是多路平衡搜索树，支持范围查询，磁盘IO取决于树高。",
                }
            )
            events = collect(socket, until={"question", "report_ready", "error"}, limit=40)
        finally:
            socket.close()
        kinds = [e["type"] for e in events]
        assert "answer_ack" in kinds and "score" in kinds, events
        assert "error" not in kinds, events
