"""隔离账户题单HTTP/WS冒烟：去重、状态、分页、重启、练习与独立清理。"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urlencode

from smoke_e2e import BACKEND, OPENER, Server, request
from practice_smoke import complete

PATH = '/api/account/question-marks'
PASSWORD = 'synthetic-question-marks-password'


def call(server, path, headers, method='GET', payload=None, status=200):
    req = urllib.request.Request(server.base + path, method=method,
        headers={**headers, 'Content-Type': 'application/json'},
        data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with OPENER.open(req, timeout=30) as response:
            assert response.status == status
            assert response.headers['Cache-Control'] == 'no-store'
            return json.loads(response.read())
    except HTTPError as error:
        assert error.code == status, (error.code, status)
        return json.loads(error.read())


async def run(server):
    accounts = [request(server.base, '/api/auth/register', {'username': name, 'password': PASSWORD}) for name in ['marks_a', 'marks_b']]
    headers, other = [{'Authorization': 'Bearer ' + user['access_token']} for user in accounts]
    call(server, PATH, {}, status=401)
    catalog = request(server.base, '/api/catalog?position=java_backend&limit=24')
    keys = []
    for row in catalog['items']:
        keys.append(call(server, PATH, headers, 'POST', {'position': row['position'], 'question_id': row['id']})['id'])
    assert len(set(keys)) == 11
    first = call(server, PATH, headers)
    assert len(first['items']) == 8 and first['has_more']
    second = call(server, PATH + '?offset=8', headers)
    assert len(second['items']) == 3 and not second['has_more']
    assert call(server, PATH, other)['total'] == 0
    row = next(row for row in first['items'] + second['items'] if row['can_practice'])
    path = PATH + '/' + row['id']
    call(server, path, other, 'PATCH', {'status': 'done', 'expected_version': 0}, status=404)
    call(server, path, headers, 'PATCH', {'status': 'done', 'expected_version': 0})
    call(server, path, headers, 'PATCH', {'status': 'todo', 'expected_version': 0}, status=409)
    call(server, path + '?expected_version=0', headers, 'DELETE', status=409)
    again = call(server, PATH, headers, 'POST', {'position': row['position'], 'question_id': row['question_id']})
    assert again == {'id': row['id'], 'reused': True}
    before = call(server, PATH + '?status=done', headers)
    assert before['total'] == 1 and before['items'][0]['version'] == 1
    search_path = PATH + '?' + urlencode({'q': row['question_id'].upper(), 'status': 'done'})
    searched = call(server, search_path, headers)
    assert searched['total'] == 1 and searched['counts']['all'] == searched['counts']['done'] == 1
    await asyncio.to_thread(server.restart)
    login = request(server.base, '/api/auth/login', {'username': 'marks_a', 'password': PASSWORD})
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert call(server, PATH + '?status=done', headers) == before
    assert call(server, search_path, headers) == searched
    practice = request(server.base, '/api/interview', {'position': row['position'], 'themes': [row['question']['theme']], 'difficulty': 'mid'}, headers)
    assert practice['account_owned'] and practice['access_token'] is None
    await complete(server, {**practice, 'access_token': login['access_token']}, [row['question']['theme']])
    assert call(server, PATH + '?status=done', headers) == before
    call(server, path + '?expected_version=1', headers, 'DELETE')
    assert call(server, PATH, headers)['total'] == 10
    assert request(server.base, '/api/account/interviews', headers=headers)['total'] == 1
    assert request(server.base, '/api/catalog?position=java_backend&limit=24') == catalog
    call(server, '/api/account', headers, 'DELETE', {'password': PASSWORD})
    call(server, PATH, headers, status=401)
    assert call(server, PATH, other)['total'] == 0
    assert not request(server.base, '/api/diagnostics/llm')['llm_configured']
    return {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
        'eleven_marks_two_pages': True, 'account_isolation': True, 'duplicate_keeps_status': True,
        'stale_patch_delete_rejected': True, 'restart_and_independent_login': True,
        'topic_practice_complete_without_mark_change': True, 'remove_preserves_bank_and_interview': True,
        'account_cleanup': True, 'search_counts_and_restart': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--json-out', type=Path); args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-marks-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'marks.sqlite3')
        try:
            server.start(); result = asyncio.run(run(server))
        finally: server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
