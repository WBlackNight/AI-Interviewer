"""Check Vite HMR entries plus real HTTP/SSE/WebSocket proxies against an offline loopback backend."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websockets


async def check(base, smoke_token=None):
    target = urlsplit(base)
    if target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost', '::1') or target.username or target.password or target.query or target.fragment or target.path not in ('', '/'):
        raise ValueError('Use a loopback development base URL')
    with httpx.Client(base_url=base, trust_env=False, timeout=15) as client:
        health = client.get('/api/health').json()
        if health.get('llm_enabled') or health.get('sandbox_enabled'):
            raise ValueError('Use an offline isolated backend for this probe')
        assistant = client.get('/assistant')
        assert assistant.status_code == 200 and '/@vite/client' in assistant.text and '/assistant/entry.tsx' in assistant.text
        demo_path = '/api/assistant/demo'
        prompt = {'position': 'java_backend', 'text': '如何安排5分钟索引练习？'}
        assert client.post(demo_path, json=prompt).status_code == 401
        if smoke_token:
            demo = client.post(demo_path, json=prompt, headers={'Authorization': 'Bearer ' + smoke_token})
            assert demo.status_code == 200 and 'text/event-stream' in demo.headers['content-type']
            assert '"type":"done"' in demo.text.replace(' ', '')
        forum_page = client.get('/forum?view=new')
        assert forum_page.status_code == 200 and 'id="forum-content"' in forum_page.text
        assert 'href="/forum"' in client.get('/').text
        forum_alias = client.get('/forum.html?view=new', follow_redirects=False)
        assert forum_alias.status_code == 308 and forum_alias.headers['location'] == '/forum?view=new'
        assert client.get('/assets/forum.js').status_code == 200
        assert isinstance(client.get('/api/forum/posts').json()['items'], list)
        response = client.post('/api/interview', json={'position': 'java_backend', 'difficulty': 'mid', 'duration_minutes': 5})
        response.raise_for_status()
        created = response.json()
        identity, credential = created['interview_id'], created['access_token']
        page = client.get('/interview/' + identity)
        assert page.status_code == 200 and '/studio/entry.tsx' in page.text and '/@vite/client' in page.text
        assert '语音练习室' in client.get('/interview/' + identity + '?mode=voice').text
        assert '实时语音陪练' in client.get('/interview/' + identity + '?mode=realtime').text
        async with websockets.connect(base.replace('http', 'ws', 1) + '/ws/interview/' + identity,
                origin=base, subprotocols=['interview', credential], proxy=None) as socket:
            await socket.send(json.dumps({'type': 'start'}))
            snapshot = json.loads(await asyncio.wait_for(socket.recv(), 20))
            assert snapshot['type'] == 'snapshot' and snapshot['current_question']['type'] == 'question'
        cancelled = client.post('/api/interview/' + identity + '/cancel', headers={'X-Interview-Token': credential})
        cancelled.raise_for_status()
    return {'passed': True, 'hmr_entries': 2, 'legacy_voice_routes': True, 'forum_proxy': True,
            'http_proxy': True, 'sse_proxy': bool(smoke_token), 'websocket_proxy': True, 'offline': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5173')
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    result = asyncio.run(check(args.base.rstrip('/'), os.environ.get('QINGZHAN_SMOKE_TOKEN')))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
