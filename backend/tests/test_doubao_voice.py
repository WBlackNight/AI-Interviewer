"""豆包JSON协议、资源释放及原面试链路；供应商连接全部用可控替身。"""
import asyncio
import base64
import json
from types import SimpleNamespace
from dataclasses import replace

import pytest

from app.config import Settings
from app.voice import doubao
from app.voice.asr import Transcript
from app.voice.channel import VoiceChannel
from app.voice.vad import EnergyVAD

OPTIONS = doubao.DoubaoVoiceOptions('private-test-key', timeout=.1, session_seconds=2)
PCM = b'\x01\x10' * 2400


class FakeSocket:
    def __init__(self, *, malformed=None, response='r1', early=False, fail_feed=False,
                 omit_chunk_id=False, no_start=False, tts_type='chat_tts_text'):
        self.inbox = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.malformed = malformed
        self.response = response
        self.early = early
        self.fail_feed = fail_feed
        self.omit_chunk_id, self.no_start, self.tts_type = omit_chunk_id, no_start, tts_type

    def emit(self, event):
        self.inbox.put_nowait(event if isinstance(event, (str, bytes)) else json.dumps(event))

    async def send(self, raw):
        event = json.loads(raw); self.sent.append(event)
        if event['type'] == 'session.create':
            self.emit(self.malformed if self.malformed is not None else {'type': 'session.created'})
        elif event['type'] == 'input_audio_buffer.append':
            if self.fail_feed:
                raise RuntimeError('private-test-key raw-provider-answer')
            if self.early:
                self.emit({'type': 'conversation.item.input_audio_transcription.completed', 'item_id': 'i', 'transcript': '原回答'})
            else:
                self.emit({'type': 'conversation.item.input_audio_transcription.delta', 'item_id': 'i', 'delta': '原'})
        elif event['type'] == 'input_audio_buffer.commit':
            self.emit({'type': 'input_audio_buffer.committed'})
            self.emit({'type': 'conversation.item.input_audio_transcription.completed', 'item_id': 'i', 'transcript': '原回答'})
        elif event['type'] == 'speech_text_buffer.commit':
            if not self.no_start:
                self.emit({'type': 'response.output_audio.started', 'response_id': 'r1', 'tts_type': self.tts_type})
            identity = {} if self.omit_chunk_id else {'response_id':self.response}
            self.emit({'type': 'response.output_audio.delta', **identity, 'delta': base64.b64encode(PCM).decode()})
            self.emit({'type': 'response.output_audio.done', **identity, 'status_code': 0})

    async def recv(self):
        return await self.inbox.get()

    async def close(self):
        self.closed = True


@pytest.fixture
def sockets(monkeypatch):
    created = []
    async def connect(endpoint, **kwargs):
        assert endpoint == doubao.ENDPOINT and kwargs['additional_headers'] == {'X-Api-Key': 'private-test-key'}
        assert kwargs['max_queue'] == 8 and kwargs['max_size'] == doubao.MAX_EVENT_BYTES
        socket = FakeSocket(); created.append(socket)
        return socket
    monkeypatch.setattr(doubao, 'connect', connect)
    return created


def test_asr_stream_commit_final_once_and_close(sockets):
    async def run():
        asr = doubao.DoubaoASR(OPTIONS)
        await asr.start()
        await asr.feed(b'\x10\x00' * 1600, sample_rate=16000)
        result = await asr.finish()
        assert result == '原回答' and await asr.finish() == ''
        assert sockets[0].closed and asr.reader is None
        kinds = [item['type'] for item in sockets[0].sent]
        assert kinds.count('input_audio_buffer.commit') == 1
        assert 'input_audio_mute.commit' in kinds and kinds[-1] == 'session.close'
        session = sockets[0].sent[0]
        assert session['session']['audio']['input']['format'] == {'type': 'pcm', 'rate': 16000}
        assert session['session']['audio']['output']['format'] == {'type': 'pcm_s16le', 'rate': 24000}
        assert session['session']['tools'] == [] and 'dialog' not in session['extension']
        assert doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


def test_tts_uses_specified_text_pcm_and_mute_without_user_audio(sockets):
    async def run():
        tts = doubao.DoubaoTTS(OPTIONS)
        chunks = [chunk async for chunk in tts.synthesize('请介绍项目。')]
        assert chunks == [PCM] and sockets[0].closed
        assert [item['type'] for item in sockets[0].sent] == [
            'session.create', 'input_audio_mute.commit', 'speech_text_buffer.commit', 'session.close']
        assert doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('raw', [b'binary', 'not-json', '[]', '{"type":5}',
    '{"type":"error","error":{"message":"private-test-key"}}'])
def test_malformed_or_error_ack_closes_without_leaking(monkeypatch, raw):
    async def run():
        socket = FakeSocket(malformed=raw)
        async def connect(*args, **kwargs): return socket
        monkeypatch.setattr(doubao, 'connect', connect)
        with pytest.raises(doubao.DoubaoVoiceError) as caught:
            await doubao.DuplexSession(OPTIONS, kind='asr').start()
        assert 'private-test-key' not in str(caught.value)
        assert socket.closed and doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


def test_mismatched_tts_response_is_never_played(monkeypatch):
    async def run():
        socket = FakeSocket(response='old-response')
        async def connect(*args, **kwargs): return socket
        monkeypatch.setattr(doubao, 'connect', connect)
        chunks = []
        with pytest.raises(doubao.DoubaoVoiceError, match='speech_mismatch'):
            async for chunk in doubao.DoubaoTTS(OPTIONS).synthesize('本题'):
                chunks.append(chunk)
        assert not chunks and socket.closed
    asyncio.run(run())


@pytest.mark.parametrize('options,error', [({'omit_chunk_id':True},None),
    ({'no_start':True},'speech_mismatch'), ({'tts_type':'normal'},'unexpected_speech')])
def test_optional_chunk_identity_still_requires_expected_audio_start(monkeypatch, options, error):
    async def run():
        socket = FakeSocket(**options)
        async def connect(*args, **kwargs): return socket
        monkeypatch.setattr(doubao, 'connect', connect)
        tts = doubao.DoubaoTTS(OPTIONS)
        if error:
            with pytest.raises(doubao.DoubaoVoiceError, match=error):
                _ = [chunk async for chunk in tts.synthesize('本题')]
        else:
            assert [chunk async for chunk in tts.synthesize('本题')] == [PCM]
        assert socket.closed and doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


def test_capacity_and_cancel_release_slots(sockets):
    async def run():
        options = replace(OPTIONS, max_connections=1)
        first = doubao.DuplexSession(options, kind='asr')
        await first.start()
        with pytest.raises(doubao.DoubaoVoiceError, match='capacity'):
            await doubao.DuplexSession(options, kind='asr').start()
        await first.close(); await first.close()
        asr = doubao.DoubaoASR(options)
        await asr.start(); await asr.close()
        assert all(socket.closed for socket in sockets) and doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


def test_unresponsive_connect_has_outer_timeout(monkeypatch):
    async def run():
        async def connect(*args, **kwargs): await asyncio.Event().wait()
        monkeypatch.setattr(doubao, 'connect', connect)
        with pytest.raises(doubao.DoubaoVoiceError, match='connect'):
            await asyncio.wait_for(doubao.DuplexSession(OPTIONS, kind='asr').start(), .5)
        assert doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('status,code', [(401,'auth'), (403,'auth'), (429,'rate_limit'), (502,'connect')])
def test_handshake_diagnostics_keep_only_status_and_safe_request_id(monkeypatch, status, code):
    class Rejected(Exception):
        response = SimpleNamespace(status_code=status, headers={'X-Tt-Logid': 'trace-12345'})
    async def run():
        async def connect(*args, **kwargs): raise Rejected('private-test-key raw-response')
        monkeypatch.setattr(doubao, 'connect', connect)
        with pytest.raises(doubao.DoubaoVoiceError) as caught:
            await doubao.DuplexSession(OPTIONS, kind='asr').start()
        assert str(caught.value) == code and caught.value.http_status == status
        assert caught.value.request_id == 'trace-12345'
        assert 'private-test-key' not in str(caught.value)
        assert doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('request_id', ['bad\nheader', 'echo-private-test-key', 123])
def test_handshake_diagnostics_drop_unsafe_or_echoed_request_id(monkeypatch, request_id):
    class Rejected(Exception):
        response = SimpleNamespace(status_code=401, headers={'X-Tt-Logid': request_id})
    async def run():
        async def connect(*args, **kwargs): raise Rejected('private-test-key')
        monkeypatch.setattr(doubao, 'connect', connect)
        with pytest.raises(doubao.DoubaoVoiceError) as caught:
            await doubao.DuplexSession(OPTIONS, kind='asr').start()
        assert caught.value.request_id is None
        assert caught.value.http_status == 401
    asyncio.run(run())


@pytest.mark.parametrize('sample_rate,pcm', [(24000, b'aa'), (16000,b'a'), (16000,b''), (16000,b'a'*6402)])
def test_invalid_pcm_rejected_before_connect(sample_rate, pcm):
    async def run():
        with pytest.raises(doubao.DoubaoVoiceError, match='input_format'):
            await doubao.DoubaoASR(OPTIONS).feed(pcm, sample_rate=sample_rate)
    asyncio.run(run())


def test_channel_feed_failure_never_commits_truncated_text():
    class BrokenASR:
        async def start(self): pass
        async def feed(self, *args, **kwargs): raise RuntimeError('private-answer')
        async def finish(self): return '不完整的转写'
        async def close(self): pass
    async def run():
        channel = VoiceChannel(vad=EnergyVAD(min_speech_ms=0), asr=BrokenASR())
        result = await channel.feed(base64.b64encode(b'\x20\x10'*1600).decode(), turn_id='a'*32, seq=0)
        assert result.utterance_ended and any(event['type']=='voice_error' for event in result.events)
        text, events = await channel.finish()
        assert text is None and not any(event['type']=='asr_final' for event in events)
    asyncio.run(run())


def test_remote_final_is_emitted_only_by_finish():
    class RemoteASR:
        async def start(self): pass
        async def feed(self, *args, **kwargs): return [Transcript('完整转写', True)]
        async def finish(self): return '完整转写'
        async def close(self): pass
    async def run():
        channel = VoiceChannel(vad=EnergyVAD(min_speech_ms=0), asr=RemoteASR())
        result = await channel.feed(base64.b64encode(b'\x20\x10'*1600).decode(), turn_id='a'*32, seq=0)
        assert result.utterance_ended and not any(event['type']=='asr_final' for event in result.events)
        text, events = await channel.finish()
        assert text == '完整转写' and len([e for e in events if e['type']=='asr_final']) == 1
        assert await channel.finish() == (None, [])
    asyncio.run(run())


def test_settings_secret_and_factory_are_explicit():
    from app.factories import build_asr, build_tts
    settings = Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao',
                        voice_tts_provider='doubao', doubao_voice_api_key='private-test-key')
    assert 'private-test-key' not in repr(settings)
    assert isinstance(build_asr(settings), doubao.DoubaoASR) and isinstance(build_tts(settings), doubao.DoubaoTTS)
    with pytest.raises(ValueError):
        Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao', doubao_voice_api_key=None)


def test_legacy_headers_use_app_id_and_token_without_api_key_or_secret(monkeypatch):
    settings = Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao',
                        doubao_voice_auth_mode='legacy', doubao_voice_api_key=None,
                        doubao_voice_app_id='123456789', doubao_voice_access_token='private-access-token')
    options = doubao.DoubaoVoiceOptions.from_settings(settings)
    headers = options.headers()
    assert headers['X-Api-App-Id'] == '123456789'
    assert headers['X-Api-Access-Key'] == 'private-access-token'
    assert headers['X-Api-Resource-Id'] == 'volc.speech.dialog'
    assert headers['X-Api-App-Key'] == 'PlgvMymc7f3tQnJ6'
    assert set(headers) == {'X-Api-App-Id','X-Api-Access-Key','X-Api-Resource-Id','X-Api-App-Key','X-Api-Request-Id'}
    assert 'private-access-token' not in repr(options) and 'private-access-token' not in repr(settings)
    assert headers['X-Api-Request-Id'] != options.headers()['X-Api-Request-Id']
    async def run():
        socket = FakeSocket()
        async def connect(endpoint, **kwargs):
            assert kwargs['additional_headers']['X-Api-Access-Key'] == 'private-access-token'
            assert 'X-Api-Key' not in kwargs['additional_headers']
            return socket
        monkeypatch.setattr(doubao, 'connect', connect)
        session = doubao.DuplexSession(options, kind='asr')
        await session.start(); await session.close()
        assert socket.closed and doubao.diagnostics()['active_connections'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('app_id,token', [(None,'private-token'), ('123',None), ('123',' ')])
def test_incomplete_legacy_settings_fail_without_echoing_credentials(app_id, token):
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None, voice_enabled=True, voice_asr_provider='doubao',
                 doubao_voice_auth_mode='legacy', doubao_voice_app_id=app_id,
                 doubao_voice_access_token=token)
    assert 'private-token' not in str(caught.value)
    with pytest.raises(doubao.DoubaoVoiceError, match='legacy_credentials_missing'):
        doubao.DoubaoVoiceOptions(auth_mode='legacy', app_id=app_id, access_token=token).headers()


def test_doubao_adapter_flows_through_authenticated_interview(monkeypatch, sockets):
    from app.api import ws
    from tests.test_voice_flow import _make_client, create_interview, open_session, send_audio, collect, LOUD
    client, factory, _asr, engine = _make_client(monkeypatch, voice_enabled=True)
    monkeypatch.setattr(ws, 'build_voice_channel', lambda settings: VoiceChannel(
        vad=EnergyVAD(min_speech_ms=200), asr=doubao.DoubaoASR(OPTIONS)))
    monkeypatch.setattr(ws, 'build_tts', lambda settings: doubao.DoubaoTTS(OPTIONS))
    with client:
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        turn = snapshot['current_question']['turn_id']
        try:
            send_audio(socket, turn, [LOUD]*3)
            socket.send_json({'type':'audio_end','turn_id':turn})
            events = collect(socket, until={'tts_end','error','tts_error'})
            assert len([e for e in events if e['type']=='asr_final']) == 1
            assert len([e for e in events if e['type']=='answer_ack']) == 1
            assert any(e['type']=='score' for e in events) and events[-1]['type']=='tts_end'
            assert any(e['type']=='tts_chunk' and e['sample_rate']==24000 for e in events)
        finally:
            socket.close()
        report = client.get('/api/interview/'+interview['interview_id']+'/report', headers={'X-Interview-Token':interview['access_token']})
        assert report.status_code == 200
    engine.dispose()


def test_stale_audio_rejected_before_provider_and_read_is_current_question(monkeypatch, sockets):
    from app.api import ws
    from tests.test_voice_flow import _make_client, create_interview, open_session, send_audio, collect, LOUD
    client, _factory, _asr, engine = _make_client(monkeypatch, voice_enabled=True)
    monkeypatch.setattr(ws, 'build_tts', lambda settings: doubao.DoubaoTTS(OPTIONS))
    with client:
        interview = create_interview(client)
        socket, snapshot = open_session(client, interview)
        try:
            send_audio(socket, 'f'*32, [LOUD]*2)
            assert socket.receive_json()['code'] == 'stale_turn'
            assert socket.receive_json()['code'] == 'stale_turn'
            assert not sockets
            socket.send_json({'type':'read_question','turn_id':snapshot['current_question']['turn_id'], 'version':snapshot['version']})
            events = collect(socket, until={'tts_end','error','tts_error'})
            assert events[-1]['type']=='tts_end' and not any(e['type']=='answer_ack' for e in events)
            assert sockets and all(s.closed for s in sockets)
            spoken = ''.join(item['text'] for s in sockets for item in s.sent if item['type']=='speech_text_buffer.commit')
            assert spoken == snapshot['current_question']['content']
        finally:
            socket.close()
    engine.dispose()
