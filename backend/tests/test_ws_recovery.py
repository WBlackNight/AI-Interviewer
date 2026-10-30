import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.models.entities import Base, InterviewRuntime, InterviewEvent, QuestionScore, Resume, TurnMetadata
from app.db import get_db
from app.schemas import AnswerMessage


@pytest.fixture
def api(monkeypatch):
    from app import main
    from app.api import ws, routes, accounts
    from app.services.accounts import AuthThrottle
    monkeypatch.setattr(accounts,'throttle',AuthThrottle())
    from app.services import account_security
    monkeypatch.setattr(account_security,'generate_code',lambda:'TEST2')
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    factory = sessionmaker(engine, expire_on_commit=False)
    config = Settings(_env_file=None, llm_api_key=None, judge0_url=None)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'SessionLocal', factory)
    monkeypatch.setattr(ws, 'SessionLocal', factory)
    monkeypatch.setattr(ws, 'settings', config)
    monkeypatch.setattr(routes, 'settings', config)
    app = main.create_app()
    def db_dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_dependency
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def create(client):
    response = client.post('/api/interview', json={'position': 'java_backend', 'difficulty': 'mid'})
    assert response.status_code == 200, response.text
    return response.json()


@contextmanager
def connect(client, interview):
    with client.websocket_connect('/ws/interview/' + interview['interview_id'],
                                  subprotocols=['interview', interview['access_token']]) as socket:
        socket.send_json({'type': 'start'})
        snapshot = socket.receive_json()
        assert snapshot['type'] == 'snapshot', snapshot
        yield socket, snapshot


def answer(snapshot, *, message_id=None, text='我不太清楚', code=None):
    payload = dict(type='answer', message_id=message_id or uuid.uuid4().hex,
                   turn_id=snapshot['current_question']['turn_id'], version=snapshot['version'], text=text)
    if code:
        payload['code'] = code
    return payload


def receive_turn(socket):
    events = []
    for _ in range(15):
        event = socket.receive_json()
        events.append(event)
        if event['type'] in ('question', 'report_ready', 'error'):
            return events
    raise AssertionError(events)


def test_resume_pii_and_access_controls(api):
    client, factory = api
    result = client.post('/api/resume', json={'resume_text':
        '专业技能\nJava、MySQL\n项目经历\n联系人13812345678 abc@example.com'}).json()
    payload = {'resume_id': result['resume_id'], 'position': 'java_backend'}
    assert client.post('/api/interview', json=payload).status_code == 403
    assert client.post('/api/interview', json=payload,
        headers={'X-Resume-Token': result['access_token']}).status_code == 200
    with factory() as db:
        raw = db.get(Resume, result['resume_id']).raw_text
        assert '13812345678' not in raw and 'abc@example.com' not in raw
    interview = create(client)
    path = f"/api/interview/{interview['interview_id']}/report"
    assert client.get(path).status_code == 403
    other = create(client)
    assert client.get(path, headers={'X-Interview-Token': other['access_token']}).status_code == 403
    response = client.get(path, headers={'X-Interview-Token': interview['access_token']})
    assert response.status_code == 200
    assert response.json()['answer_count'] == 0


def test_ws_token_and_origin(api):
    client, _ = api
    interview = create(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/interview/' + interview['interview_id']):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/interview/' + interview['interview_id'],
            subprotocols=['interview', interview['access_token']], headers={'origin': 'https://evil.example'}):
            pass


def test_duplicate_answer_and_payload_conflict(api):
    client, factory = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        payload = answer(snapshot)
        socket.send_json(payload)
        first = receive_turn(socket)
        socket.send_json(payload)
        assert receive_turn(socket) == first
        socket.send_json({**payload, 'text': '不同内容'})
        assert socket.receive_json()['code'] == 'message_conflict'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 1
        assert db.scalar(select(func.count()).select_from(TurnMetadata)) == 1


def test_reconnect_probe_and_stale_answer(api):
    client, factory = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        payload = answer(snapshot)
        socket.send_json(payload)
        first = receive_turn(socket)
        probe = first[-1]
        assert probe['is_probe']
        assert first[0]['question_id'] == snapshot['current_question']['id']
    with connect(client, interview) as (socket, resumed):
        assert resumed['current_question'] == probe
        assert resumed['version'] == 2
        socket.send_json({**payload, 'message_id': uuid.uuid4().hex})
        assert socket.receive_json()['code'] == 'stale_turn'
        socket.send_json(answer(resumed, text='索引支持范围查询的实际使用场景'))
        second = receive_turn(socket)
        assert second[0]['question_id'] == probe['id']
    with factory() as db:
        events = list(db.scalars(select(InterviewEvent).order_by(InterviewEvent.id)))
        assert [e.seq for e in events] == list(range(len(events)))
        rows = list(db.scalars(select(QuestionScore).order_by(QuestionScore.id)))
        assert rows[1].content == probe['content'] and rows[1].question_id == probe['id']
    from app.api.ws import manager
    assert not manager._locks


@pytest.mark.parametrize('message', [[], None, {'type': 'answer'}, {'type': 'unknown'},
    {'type': 'start', 'extra': 1}])
def test_bad_messages_do_not_advance(api, message):
    client, factory = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        socket.send_json(message)
        assert socket.receive_json()['code'] == 'invalid_message'
        socket.send_json({'type': 'start'})
        assert socket.receive_json()['current_question'] == snapshot['current_question']
    with factory() as db:
        assert db.get(InterviewRuntime, interview['interview_id']).version == 1


def test_empty_and_oversized_code_do_not_advance(api):
    client, _ = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        socket.send_json(answer(snapshot, text=''))
        assert socket.receive_json()['code'] == 'invalid_answer'
        socket.send_json(answer(snapshot, code='中' * 6000))
        assert socket.receive_json()['code'] == 'invalid_message'
        socket.send_json({'type': 'start'})
        assert socket.receive_json()['version'] == 1


def test_binary_frame_does_not_break_text_session(api):
    client, _ = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        socket.send_bytes(b'not text')
        assert socket.receive_json()['code'] == 'invalid_message'
        socket.send_json({'type': 'start'})
        assert socket.receive_json()['current_question'] == snapshot['current_question']


def test_long_answer_is_preserved(api):
    client, factory = api
    interview = create(client)
    content = '解释实现原理以及项目取舍' * 300
    with connect(client, interview) as (socket, snapshot):
        socket.send_json(answer(snapshot, text=content))
        events = receive_turn(socket)
        assert events[0]['answer_text'] == content
    with factory() as db:
        assert db.scalar(select(QuestionScore)).answer_text == content


def test_atomic_rollback_and_retry(api, monkeypatch):
    from app import repositories
    client, factory = api
    interview = create(client)
    original = repositories.save_score_records
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('模拟评分落库失败')
    with connect(client, interview) as (socket, snapshot):
        payload = answer(snapshot)
        monkeypatch.setattr(repositories, 'save_score_records', fail)
        socket.send_json(payload)
        assert socket.receive_json()['retryable']
        with factory() as db:
            assert db.get(InterviewRuntime, interview['interview_id']).version == 1
            assert db.scalar(select(func.count()).select_from(QuestionScore)) == 0
        monkeypatch.setattr(repositories, 'save_score_records', original)
        socket.send_json(payload)
        assert receive_turn(socket)[0]['type'] == 'answer_ack'


def test_finished_restart_and_report(api, monkeypatch):
    client, factory = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        for _ in range(35):
            socket.send_json(answer(snapshot))
            events = receive_turn(socket)
            assert events[-1]['type'] != 'error'
            if events[-1]['type'] == 'report_ready':
                break
            snapshot = {'current_question': events[-1], 'version': events[-1]['version']}
        else:
            pytest.fail('面试未能完成')
    # 没有任何缓存状态，重新构造 SessionManager 相当于进程重新读取数据库。
    from app.api import ws
    monkeypatch.setattr(ws, 'manager', ws.SessionManager())
    with connect(client, interview) as (_, resumed):
        assert resumed['finished'] and resumed['current_question'] is None
        assert sum(e['type'] == 'greeting' for e in resumed['events']) == 1
    report = client.get(f"/api/interview/{interview['interview_id']}/report",
                        headers={'X-Interview-Token': interview['access_token']}).json()
    assert report['is_complete'] and report['answer_count'] > report['question_count']
    assert any('#p' in r['question_id'] for r in report['per_question'])
    assert all(r['answer_text'] for r in report['per_question'])


def test_second_connection_cannot_answer_previous_turn(api):
    client, factory = api
    interview = create(client)
    with connect(client, interview) as (first, snapshot):
        with connect(client, interview) as (second, same):
            first.send_json(answer(snapshot))
            receive_turn(first)
            second.send_json(answer(same))
            assert second.receive_json()['code'] == 'stale_turn'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 1


def test_event_migration_preserves_old_rows_and_enforces_sequence():
    from app.migrations import upgrade_event_sequences
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE interview_event (id INTEGER PRIMARY KEY, '
            'interview_id TEXT, seq INTEGER, type TEXT, payload JSON, created_at DATETIME)'))
        conn.execute(text("INSERT INTO interview_event VALUES (1, 'old', 0, 'state', '{}', NULL), "
                          "(2, 'old', 0, 'question', '{}', NULL)"))
    upgrade_event_sequences(engine)
    upgrade_event_sequences(engine)
    with engine.connect() as conn:
        assert list(conn.execute(text('SELECT id, seq FROM interview_event ORDER BY id'))) == [(1, 0), (2, 1)]
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO interview_event VALUES (3, 'old', 0, 'state', '{}', NULL)"))
    engine.dispose()
