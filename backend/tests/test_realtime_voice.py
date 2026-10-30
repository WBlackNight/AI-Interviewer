"""实时S2S的持续会话、打断白名单、边界与鉴权回归；不调用供应商。"""
import asyncio
import base64
from threading import Event
import pytest
from starlette.websockets import WebSocketDisconnect

from app.voice import realtime
from app.voice.doubao import DoubaoVoiceError, DoubaoVoiceOptions

PCM = base64.b64encode(b'\x01\x10' * 1600).decode()


class Session:
    instances = []
    def __init__(self, *args, **kwargs):
        self.sent, self.closed = [], False
        self.closed_event = Event()
        self.inbox = asyncio.Queue()
        self.instances.append(self)
    async def start(self, **kwargs):
        assert '陪练' in kwargs['instructions']
        self.instructions = kwargs['instructions']
    async def send(self, kind, **kwargs):
        self.sent.append(kind)
        if kind == 'input_audio_buffer.append':
            for event in [
                {'type': 'conversation.item.input_audio_transcription.started'},
                {'type': 'conversation.item.input_audio_transcription.completed', 'transcript': '测试发言'},
                {'type': 'response.output_audio.started'},
                {'type': 'response.output_audio.delta', 'delta': PCM},
                {'type': 'response.output_audio.done'},
            ]:
                await self.inbox.put(event)
        if kind == 'response.cancel':
            await self.inbox.put({'type': 'response.canceled'})
    async def receive(self):
        return await self.inbox.get()
    async def close(self):
        self.closed = True
        self.closed_event.set()


def test_two_inputs_share_connection_and_pause_unmute(monkeypatch):
    monkeypatch.setattr(realtime, 'DuplexSession', Session)
    async def run():
        dialogue = realtime.RealtimeDialogue(DoubaoVoiceOptions('test'))
        await dialogue.start()
        for seq in range(2):
            await dialogue.accept({'type': 'audio', 'seq': seq, 'data': PCM})
            await dialogue.accept({'type': 'pause'})
        assert dialogue.session.sent.count('input_audio_unmute.commit') == 2
        assert dialogue.session.sent.count('input_audio_buffer.append') == 2
        await dialogue.close()
        assert dialogue.session.closed
    asyncio.run(run())


@pytest.mark.parametrize('event', [
    {'type': 'audio', 'seq': 1, 'data': PCM}, {'type': 'audio', 'seq': True, 'data': PCM},
    {'type': 'audio', 'seq': 0, 'data': '!!!'}, {'type': 'audio', 'seq': 0, 'data': 'AA=='},
    {'type': 'audio', 'seq': 0, 'data': PCM * 3}, {'type': 'pause', 'extra': 1},
    {'type': 'session.update', 'instructions': 'arbitrary'}, {'type': 'audio', 'seq': 0, 'data': []},
])
def test_input_rejected_without_forwarding(monkeypatch, event):
    monkeypatch.setattr(realtime, 'DuplexSession', Session)
    async def run():
        dialogue = realtime.RealtimeDialogue(DoubaoVoiceOptions('test'))
        with pytest.raises(DoubaoVoiceError):
            await dialogue.accept(event)
        assert not dialogue.session.sent
    asyncio.run(run())


def test_interrupt_and_event_whitelist(monkeypatch):
    monkeypatch.setattr(realtime, 'DuplexSession', Session)
    async def run():
        dialogue = realtime.RealtimeDialogue(DoubaoVoiceOptions('test'))
        assert dialogue.translate({'type': 'response.output_audio.delta', 'delta': PCM}) is None
        assert dialogue.translate({'type': 'response.output_audio.started'})['type'] == 'speaking'
        assert dialogue.translate({'type': 'response.output_audio.delta', 'delta': PCM})['data'] == PCM
        await dialogue.accept({'type': 'interrupt'})
        assert dialogue.session.sent == ['response.cancel']
        assert dialogue.translate({'type': 'response.output_audio.started'}) is None
        assert dialogue.translate({'type': 'response.output_audio.delta', 'delta': PCM}) is None
        assert dialogue.translate({'type': 'conversation.item.input_audio_transcription.started'})['type'] == 'listening'
        dialogue.translate({'type': 'conversation.item.input_audio_transcription.completed', 'transcript': '下一轮'})
        assert dialogue.translate({'type': 'response.output_audio.started'})['type'] == 'speaking'
        assert dialogue.translate({'type': 'response.function_call_arguments.done', 'secret': 'x'}) is None
        assert dialogue.translate({'type': 'response.done', 'usage': {'private': 1}}) is None
        with pytest.raises(DoubaoVoiceError):
            dialogue.translate({'type': 'response.output_audio.delta', 'delta': 'AA=='})
    asyncio.run(run())


def test_authenticated_route_two_rounds_and_wrong_owner(monkeypatch):
    from app.api import realtime as route
    from tests.test_voice_flow import _make_client, create_interview
    from app.config import Settings
    client, factory, _, engine = _make_client(monkeypatch, voice_enabled=True)
    config = Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao', voice_tts_provider='doubao', doubao_voice_api_key='test')
    monkeypatch.setattr(route, 'get_settings', lambda: config)
    monkeypatch.setattr(route, 'SessionLocal', factory)
    monkeypatch.setattr(realtime, 'DuplexSession', Session)
    Session.instances.clear()
    with client:
        interview = create_interview(client)
        url = '/ws/realtime/' + interview['interview_id']
        protocols = ['interview', interview['access_token']]
        for token, origin in [('f' * 64, config.cors_origins[0]), (interview['access_token'], 'https://untrusted.invalid')]:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(url, subprotocols=['interview', token], headers={'origin': origin}):
                    pass
        assert not Session.instances
        with client.websocket_connect(url, subprotocols=protocols, headers={'origin': config.cors_origins[0]}) as socket:
            assert socket.receive_json()['type'] == 'ready'
            for seq in range(2):
                socket.send_json({'type': 'audio', 'seq': seq, 'data': PCM})
                events = []
                while not events or events[-1]['type'] != 'audio_end':
                    events.append(socket.receive_json())
                assert any(e['type'] == 'caption' and e['text'] == '测试发言' for e in events)
                assert any(e['type'] == 'audio' for e in events)
            socket.send_json({'type': 'interrupt'})
            assert socket.receive_json()['type'] == 'interrupted'
        assert len(Session.instances) == 1 and Session.instances[0].closed_event.wait(2)
    engine.dispose()


def test_context_is_private_read_only_and_used_by_dialogue(monkeypatch):
    from app.api import realtime as route
    from app.models.entities import InterviewRuntime
    from tests.test_voice_flow import _make_client, create_interview
    client, factory, _, engine = _make_client(monkeypatch, voice_enabled=True)
    monkeypatch.setattr(route, 'SessionLocal', factory)
    monkeypatch.setattr(realtime, 'DuplexSession', Session)
    with client:
        interview = create_interview(client)
        url = '/api/interview/' + interview['interview_id'] + '/realtime-context'
        headers = {'X-Interview-Token': interview['access_token']}
        assert client.get(url).status_code == 403
        with factory() as db:
            runtime = db.get(InterviewRuntime, interview['interview_id'])
            runtime.snapshot = {'question_event': {'content': '解释B+树的范围查询', 'theme': 'MySQL', 'private': 'not-exposed'}, 'resume': 'private'}
            db.commit()
        before = len(Session.instances)
        response = client.get(url, headers=headers)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert response.json() == {'question': {'content': '解释B+树的范围查询', 'theme': 'MySQL'}}
        assert len(Session.instances) == before
        async def run():
            dialogue = realtime.RealtimeDialogue(DoubaoVoiceOptions('test'))
            await dialogue.start(response.json()['question'])
            assert '解释B+树的范围查询' in dialogue.session.instructions
            assert 'private' not in dialogue.session.instructions
            await dialogue.close()
        asyncio.run(run())
        with factory() as db:
            interview_row = route.get_interview(db, interview['interview_id'])
            interview_row.status = 'finished'
            db.commit()
        assert client.get(url, headers=headers).status_code == 409
    engine.dispose()


@pytest.mark.parametrize('failure,code', [(DoubaoVoiceError('capacity'), 'capacity'),
    (DoubaoVoiceError('private upstream message', http_status=401), 'provider_auth')])
def test_route_failure_is_actionable_without_exposing_provider_details(monkeypatch, failure, code):
    from app.api import realtime as route
    from tests.test_voice_flow import _make_client, create_interview
    from app.config import Settings
    client, factory, _, engine = _make_client(monkeypatch, voice_enabled=True)
    config = Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao', voice_tts_provider='doubao', doubao_voice_api_key='test')
    monkeypatch.setattr(route, 'get_settings', lambda: config)
    monkeypatch.setattr(route, 'SessionLocal', factory)
    class FailingSession(Session):
        async def start(self, **kwargs):
            raise failure
    monkeypatch.setattr(realtime, 'DuplexSession', FailingSession)
    with client:
        interview = create_interview(client)
        with client.websocket_connect('/ws/realtime/' + interview['interview_id'],
                subprotocols=['interview', interview['access_token']], headers={'origin': config.cors_origins[0]}) as socket:
            assert socket.receive_json() == {'type': 'error', 'code': code}
        assert Session.instances[-1].closed_event.wait(2)
    engine.dispose()
