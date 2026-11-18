"""Cloud configuration and proxy regressions; no Docker daemon or external API calls."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest
import yaml
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.services.web_origin import allowed_origin

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ('tools/' + name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cloud_root(tmp_path):
    directory = tmp_path / 'deploy/cloud'
    directory.mkdir(parents=True)
    shutil.copyfile(ROOT / 'deploy/cloud/app.env.example', directory / 'app.env.example')
    return tmp_path


def test_ip_setup_creates_private_stable_settings_without_local_env(cloud_root):
    setup = load('cloud_setup')
    target = setup.setup(cloud_root, ip='8.8.8.8')
    assert target == 'qingzhan.8-8-8-8.sslip.io'
    private = cloud_root / 'deploy/cloud/app.env'
    first = setup.read_env(private)
    assert json.loads(first['CORS_ORIGINS']) == ['https://' + target]
    assert len(first['AUTH_CHALLENGE_SECRET']) >= 32
    assert first['DATABASE_URL'] == 'sqlite:////srv/state/app.sqlite3'
    setup.setup(cloud_root, ip='8.8.8.8')
    assert setup.read_env(private) == first
    assert not (cloud_root / 'backend/.env').exists()
    with pytest.raises(ValueError):
        setup.setup(cloud_root, host='new.example.org')
    assert setup.read_env(private) == first


@pytest.mark.parametrize('ip', ['127.0.0.1', '192.168.1.1', '0.0.0.0', '2001:4860:4860::8888', 'not-ip'])
def test_cloud_ip_requires_public_ipv4(ip):
    with pytest.raises(ValueError):
        load('cloud_setup').hostname(ip=ip)


@pytest.mark.parametrize('host', ['https://example.org', 'example.org:443', 'example.org/x', 'example.org { respond hacked }', '*.example.org', '8.8.8.8'])
def test_cloud_host_rejects_config_injection(host):
    with pytest.raises(ValueError):
        load('cloud_setup').hostname(host=host)


def test_voice_key_is_preserved_raw_and_never_overwrites_other_configuration(cloud_root):
    setup = load('cloud_setup')
    setup.setup(cloud_root, host='interview.example.org')
    path = cloud_root / 'deploy/cloud/app.env'
    original = setup.read_env(path)
    key = 'synthetic-$speech#key'
    setup.configure_voice(cloud_root, key)
    result = setup.read_env(path)
    assert result['DOUBAO_VOICE_API_KEY'] == key
    assert result['VOICE_ENABLED'] == 'true'
    assert result['VOICE_ASR_PROVIDER'] == result['VOICE_TTS_PROVIDER'] == 'doubao'
    assert result['AUTH_CHALLENGE_SECRET'] == original['AUTH_CHALLENGE_SECRET']
    before = path.read_bytes()
    for invalid in ('', 'x\nKEY=oops', 'x\rKEY=oops'):
        with pytest.raises(ValueError):
            setup.configure_voice(cloud_root, invalid)
    assert path.read_bytes() == before


def test_cloud_services_publish_only_proxy_and_persist_data():
    services = yaml.safe_load((ROOT / 'compose.cloud.yml').read_text(encoding='utf-8'))['services']
    assert 'ports' not in services['app']
    assert services['app']['env_file'][0]['format'] == 'raw'
    assert services['app']['read_only'] is True
    assert services['app']['volumes'] == ['app_data:/srv/state']
    assert {'80:80', '443:443'}.issubset(services['caddy']['ports'])
    assert services['caddy']['depends_on']['app']['condition'] == 'service_healthy'


def test_forwarded_https_preserves_voice_origin_checks():
    app = FastAPI()

    @app.websocket('/ws/proxy-check')
    async def check(socket: WebSocket):
        if not allowed_origin(socket, []):
            await socket.close(4403)
            return
        await socket.accept()
        await socket.send_json({'scheme': socket.scope['scheme']})
        await socket.close()

    with TestClient(ProxyHeadersMiddleware(app, trusted_hosts='*')) as client:
        with client.websocket_connect('/ws/proxy-check', headers={
                'host': 'interview.example.org', 'origin': 'https://interview.example.org',
                'x-forwarded-proto': 'https'}) as socket:
            assert socket.receive_json()['scheme'] == 'wss'
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws/proxy-check', headers={
                    'host': 'interview.example.org', 'origin': 'https://evil.example.org',
                    'x-forwarded-proto': 'https'}):
                pytest.fail('Wrong origin was accepted')


def test_cloud_check_requires_tls_and_never_claims_audio_quality(monkeypatch):
    check = load('cloud_check')
    for url in ('http://example.org', 'https://user:secret@example.org', 'https://example.org/path'):
        with pytest.raises(ValueError):
            check.base_url(url)
    monkeypatch.setattr(check, 'get_json', lambda url: {'status': 'ok', 'question_count': 120}
        if url.endswith('/health') else {'enabled': True, 'realtime_enabled': True, 'demo_only': False})
    report = check.check_http('https://interview.example.org', require_voice=True)
    assert report['passed'] and report['voice_config_enabled']
    assert not report['provider_session_tested'] and not report['microphone_tested'] and not report['end_to_end_verified']
