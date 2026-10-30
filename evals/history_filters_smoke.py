"""真实HTTP/WS记录筛选、状态统计、重新登录和重启冒烟；仅合成数据。"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from urllib.parse import urlencode
import uuid

import websockets

from smoke_e2e import BACKEND, Server, request
from practice_smoke import complete, denied
from account_smoke import delete


async def seed_states(server, token):
    headers = {'Authorization': 'Bearer ' + token}
    result = []
    for position, theme, difficulty in [('java_backend', 'MySQL', 'easy'),
                                         ('python_backend', 'Python基础', 'hard'),
                                         ('java_backend', 'MySQL', 'mid')]:
        result.append(request(server.base, '/api/interview', {'position': position, 'themes': [theme], 'difficulty': difficulty}, headers))
    running = result[1]['interview_id']
    async with websockets.connect(server.base.replace('http', 'ws', 1) + '/ws/interview/' + running,
                                  subprotocols=['interview', token]) as ws:
        await ws.send(json.dumps({'type': 'start'}))
        snapshot = json.loads(await asyncio.wait_for(ws.recv(), 15))
        assert snapshot['type'] == 'snapshot' and not snapshot['finished']
    request(server.base, '/api/interview/' + result[2]['interview_id'] + '/cancel', {}, {'X-Interview-Token': token})
    return result


async def run(server):
    password = 'synthetic-history-' + uuid.uuid4().hex
    owner, other = [request(server.base, '/api/auth/register', {'username': name, 'password': password})
                    for name in ('history_owner', 'history_other')]
    auth = lambda user: {'Authorization': 'Bearer ' + user['access_token']}
    def history(user, **params):
        return request(server.base, '/api/account/interviews?' + urlencode(params), headers=auth(user))
    records = await seed_states(server, owner['access_token'])
    finished = request(server.base, '/api/interview', {'position': 'python_backend', 'themes': ['Python基础']}, auth(owner))
    report, _, _ = await complete(server, {**finished, 'access_token': owner['access_token']}, ['Python基础'])
    request(server.base, '/api/interview', {'position': 'java_backend', 'themes': ['MySQL']}, auth(other))
    initial = history(owner)
    assert initial['total'] == 4 and initial['status_counts'] == dict.fromkeys(['created', 'running', 'finished', 'cancelled'], 1)
    assert history(other)['total'] == 1
    running = history(owner, status='running', position='python_backend', difficulty='hard', limit=1)
    assert running['total'] == 1 and running['items'][0]['interview_id'] == records[1]['interview_id']
    assert running['status_counts'] == {'created': 0, 'running': 1, 'finished': 0, 'cancelled': 0}
    assert history(owner, status='created', position='python_backend')['total'] == 0
    assert history(owner, position='java_backend')['total'] == 2
    ids = [history(owner, limit=1, offset=index)['items'][0]['interview_id'] for index in range(4)]
    assert len(set(ids)) == 4
    denied(server.base, '/api/account/interviews?status=finished', status=401)
    await asyncio.to_thread(server.restart)
    login = request(server.base, '/api/auth/login', {'username': 'history_owner', 'password': password})
    assert history(login)['items'] == initial['items']
    assert history(login, status='running', difficulty='hard')['items'] == running['items']
    assert request(server.base, '/api/interview/' + finished['interview_id'] + '/report',
                   headers={'X-Interview-Token': login['access_token']}) == report
    request(server.base, '/api/auth/logout', {}, auth(login))
    denied(server.base, '/api/account/interviews', headers=auth(login), status=401)
    assert history(owner)['total'] == 4
    request(server.base, '/api/interview/' + records[1]['interview_id'] + '/cancel', {}, {'X-Interview-Token': owner['access_token']})
    assert delete(server.base, '/api/account', auth(owner), {'password': password})['deleted']
    assert history(other)['total'] == 1
    return {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
            'all_four_statuses': True, 'combined_position_difficulty_status': True,
            'scoped_counts': True, 'stable_pagination': True, 'restart_and_independent_login': True,
            'report_unchanged': True, 'logout_session_scoped': True, 'cross_account_isolation': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-history-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'history.sqlite3')
        try:
            server.start()
            result = asyncio.run(run(server))
        finally:
            server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
