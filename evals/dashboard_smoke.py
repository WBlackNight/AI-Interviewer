"""真实HTTP/WS：完成练习后概览计数、日期任务、清空笔记及重启恢复；仅合成数据。"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile

from smoke_e2e import BACKEND, Server, request
from practice_smoke import complete, denied
from revision_smoke import update
from revision_notes_smoke import put


async def run(server):
    password = 'synthetic-dashboard-password'
    owner = request(server.base, '/api/auth/register', {'username': 'dashboard_owner', 'password': password})
    other = request(server.base, '/api/auth/register', {'username': 'dashboard_other', 'password': password})
    headers = {'Authorization': 'Bearer ' + owner['access_token']}
    def overview(auth=headers):
        return request(server.base, '/api/account/dashboard', headers=auth)
    assert sum(row['finished'] for row in overview()['week']) == 0
    created = request(server.base, '/api/interview', {'position': 'python_backend', 'themes': ['Python基础']}, headers)
    await complete(server, {**created, 'access_token': owner['access_token']}, ['Python基础'])
    tasks = request(server.base, '/api/account/interviews/' + created['interview_id'] + '/revision-tasks', {}, headers)
    task = tasks['items'][0]
    today = overview()['today']
    update(server.base, '/api/account/revision-tasks/' + task['id'], headers, {'due_date': today})
    put(server.base, '/api/account/revision-tasks/' + task['id'] + '/note', headers, 'Synthetic note must not appear in dashboard', 0)
    initial = overview()
    assert initial['interviews']['finished'] == initial['week'][-1]['finished'] == 1
    assert initial['tasks']['today'] == initial['notes_with_content'] == 1
    assert initial['priority_tasks'][0]['id'] == task['id']
    assert 'Synthetic note' not in json.dumps(initial)
    assert overview({'Authorization': 'Bearer ' + other['access_token']})['interviews']['finished'] == 0
    denied(server.base, '/api/account/dashboard', status=401)
    await asyncio.to_thread(server.restart)
    assert overview() == initial
    login = request(server.base, '/api/auth/login', {'username': 'dashboard_owner', 'password': password})
    assert overview({'Authorization': 'Bearer ' + login['access_token']}) == initial
    put(server.base, '/api/account/revision-tasks/' + task['id'] + '/note', headers, '', 1)
    update(server.base, '/api/account/revision-tasks/' + task['id'], headers, {'status': 'done'})
    final = overview()
    assert final['notes_with_content'] == final['tasks']['today'] == 0
    assert final['tasks']['done'] == 1 and final['week'][-1]['finished'] == 1
    return {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
            'real_completed_interview_counted_today': True, 'calendar_task_and_note_counts': True,
            'cross_account_and_auth': True, 'no_private_content_in_summary': True,
            'restart_and_independent_login': True, 'clear_note_and_finish_task': True,
            'manual_task_status_does_not_change_interview_count': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-dashboard-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'dashboard.sqlite3')
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
