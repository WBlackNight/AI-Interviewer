"""Check HTTPS/API configuration; --real-voice explicitly opens one paid-capable provider session."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def base_url(value):
    parsed = urlsplit(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or not parsed.hostname or parsed.scheme not in ('http', 'https')):
        raise ValueError('请输入不含凭据、路径和参数的站点地址。')
    if parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('公网检查必须使用HTTPS；HTTP仅允许本机诊断。')
    return value.rstrip('/')


def get_json(url):
    with urlopen(Request(url, headers={'Accept': 'application/json'}), timeout=15) as response:
        if urlsplit(response.url).scheme != urlsplit(url).scheme:
            raise ValueError('检查地址发生协议变化，请使用最终HTTPS入口。')
        body = response.read(65537)
        if len(body) > 65536:
            raise ValueError('诊断响应超出上限。')
        return json.loads(body)


def check_http(url, *, require_voice=False):
    url = base_url(url)
    health = get_json(url + '/api/health')
    voice = get_json(url + '/api/voice/config')
    active = voice.get('enabled') is True and voice.get('realtime_enabled') is True and voice.get('demo_only') is False
    return {'api_healthy': health.get('status') == 'ok', 'question_count': health.get('question_count'),
            'https': url.startswith('https://'), 'voice_config_enabled': active,
            'passed': health.get('status') == 'ok' and (active or not require_voice),
            'provider_session_tested': False, 'microphone_tested': False, 'end_to_end_verified': False}


async def check_provider():
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.config import Settings
    from app.voice.doubao import DuplexSession, DoubaoVoiceOptions, DoubaoVoiceError
    try:
        settings = Settings(_env_file=None)
        if not settings.voice_enabled or (settings.voice_asr_provider, settings.voice_tts_provider) != ('doubao', 'doubao'):
            return {'provider_session_ready': False, 'error_code': 'voice_not_enabled'}
        session = DuplexSession(DoubaoVoiceOptions.from_settings(settings), kind='cloud_check')
        try:
            await asyncio.wait_for(session.start(instructions='这是连接诊断。不要主动说话，不调用工具。'), timeout=30)
            return {'provider_session_ready': True}
        except DoubaoVoiceError as error:
            return {'provider_session_ready': False, 'error_code': str(error), 'http_status': error.http_status}
        except (TimeoutError, OSError):
            return {'provider_session_ready': False, 'error_code': 'provider_network_or_timeout'}
        finally:
            await session.close()
    except Exception:
        return {'provider_session_ready': False, 'error_code': 'invalid_server_configuration'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--require-voice', action='store_true')
    parser.add_argument('--real-voice', action='store_true', help='在app容器内运行，使用服务端密钥建立一次真实语音连接，可能计费')
    args = parser.parse_args()
    try:
        report = check_http(args.url, require_voice=args.require_voice)
        if args.real_voice:
            report.update(asyncio.run(check_provider()), provider_session_tested=True)
            report['passed'] = report['passed'] and report['provider_session_ready']
    except (ValueError, OSError, HTTPError, URLError):
        report = {'passed': False, 'error_code': 'https_or_api_unreachable',
                  'hint': '检查地址、可信证书、80/443端口、DNS与容器日志；本工具不会忽略证书错误。'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
