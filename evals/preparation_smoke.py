"""隔离准备计划HTTP/WS：并发复用、完整练习、重启与独立删除，不调用模型。"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile

from smoke_e2e import BACKEND, Server, request
from question_marks_smoke import call
from practice_smoke import complete

PATH = '/api/account/preparation-plans'
PASSWORD = 'synthetic-preparation-password'


async def run(server):
    users = [request(server.base, '/api/auth/register', {'username': name, 'password': PASSWORD}) for name in ['prepare_a', 'prepare_b']]
    headers, other = [{'Authorization': 'Bearer ' + row['access_token']} for row in users]
    created = call(server, PATH, headers, 'POST', {'name': 'Python准备计划', 'position': 'python_backend',
        'themes': ['Python基础'], 'difficulty': 'hard', 'target_date': '2026-12-01'})
    key = created['id']; base = PATH + '/' + key
    assert request(server.base, '/api/account/interviews', headers=headers)['total'] == 0
    call(server, base + '/practice', other, 'POST', {'expected_version': 0}, status=404)
    results = await asyncio.gather(*[asyncio.to_thread(call, server, base + '/practice', headers, 'POST', {'expected_version': 0}) for _ in range(4)])
    assert len({row['interview_id'] for row in results}) == 1 and sum(row['reused'] for row in results) == 3
    first = results[0]['interview_id']
    await complete(server, {**results[0], 'access_token': users[0]['access_token']}, ['Python基础'])
    themed = call(server, base + '/review', headers)
    assert themed['total'] == 1 and themed['theme'] == 'Python基础'
    assert themed['items'][0]['interview_id'] == first
    call(server, base + '/review', other, status=404)
    tasks = call(server, '/api/account/interviews/' + first + '/revision-tasks', headers, 'POST')
    task = tasks['items'][0]
    call(server, '/api/account/revision-tasks/' + task['id'], headers, 'PATCH', {'status': 'done'})
    duplicate = call(server, '/api/account/interviews/' + first + '/revision-tasks', headers, 'POST')
    assert duplicate['added'] == 0 and duplicate['items'][0]['status'] == 'done'
    assert call(server, base + '/review', headers) == themed
    source = call(server, PATH + '/source/' + first, headers)['source']
    assert source['id'] == key and source['name'] == 'Python准备计划'
    call(server, PATH + '/source/' + first, other, status=404)
    assert call(server, '/api/account/dashboard', headers)['preparation']['items'][0]['id'] == key
    row = call(server, PATH, headers)['items'][0]
    assert row['finished_count'] == 1 and row['version'] == 0 and row['target_date'] == '2026-12-01'
    first_history = call(server, base + '/practices', headers)
    assert first_history['total'] == 1 and first_history['status_counts']['finished'] == 1
    call(server, base + '/practices', other, status=404)
    second = call(server, base + '/practice', headers, 'POST', {'expected_version': 0})
    assert second['interview_id'] != first and not second['reused']
    filtered = call(server, base + '/practices?status=created&limit=1', headers)
    assert filtered['total'] == 1 and filtered['status_counts']['finished'] == 1
    assert filtered['items'][0]['interview_id'] == second['interview_id']
    call(server, '/api/account/interviews/' + first, headers, 'DELETE')
    assert call(server, PATH, headers)['items'][0]['finished_count'] == 0
    request(server.base, '/api/interview/' + second['interview_id'] + '/cancel', {}, {'X-Interview-Token': users[0]['access_token']})
    call(server, base, headers, 'PATCH', {'name': '调整后的计划', 'target_date': None, 'status': 'archived', 'expected_version': 0})
    call(server, base, headers, 'PATCH', {'name': 'stale', 'expected_version': 0}, status=409)
    call(server, base + '/practice', headers, 'POST', {'expected_version': 1}, status=409)
    assert call(server, PATH + '/source/' + second['interview_id'], headers)['source']['status'] == 'archived'
    assert call(server, '/api/account/dashboard', headers)['preparation']['counts']['active'] == 0
    before = call(server, PATH, headers)
    history_before = call(server, base + '/practices', headers)
    assert history_before['status_counts'] == {'created': 0, 'running': 0, 'finished': 0, 'cancelled': 1}
    await asyncio.to_thread(server.restart)
    login = request(server.base, '/api/auth/login', {'username': 'prepare_a', 'password': PASSWORD})
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert call(server, PATH, headers) == before
    assert call(server, base + '/practices', headers) == history_before
    assert call(server, base + '/review', headers)['total'] == 0
    assert call(server, PATH + '?plan_id=' + key, headers)['items'][0]['name'] == '调整后的计划'
    assert call(server, PATH + '/source/' + second['interview_id'], headers)['source']['name'] == '调整后的计划'
    call(server, base, headers, 'PATCH', {'status': 'active', 'expected_version': 1})
    third = call(server, base + '/practice', headers, 'POST', {'expected_version': 2})
    assert third['interview_id'] not in [first, second['interview_id']]
    call(server, base, headers, 'PATCH', {'status': 'archived', 'expected_version': 2})
    call(server, base + '?expected_version=3', headers, 'DELETE')
    assert call(server, PATH, headers)['total'] == 0
    call(server, base + '/practices', headers, status=404)
    call(server, base + '/review', headers, status=404)
    assert call(server, PATH + '/source/' + third['interview_id'], headers)['source'] is None
    assert call(server, '/api/account/dashboard', headers)['preparation']['counts'] == {'active': 0, 'archived': 0, 'past_target': 0}
    assert request(server.base, '/api/account/interviews', headers=headers)['total'] == 2
    call(server, '/api/account', headers, 'DELETE', {'password': PASSWORD})
    assert call(server, PATH, other)['total'] == 0
    call(server, PATH, headers, status=401)
    assert not request(server.base, '/api/diagnostics/llm')['llm_configured']
    return {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
        'save_does_not_create_interview': True, 'four_concurrent_starts_reuse_one': True,
        'complete_practice_and_manual_metadata_independent': True, 'archive_version_and_restore': True,
        'restart_independent_login': True, 'interview_delete_recounts': True,
        'plan_delete_preserves_interviews': True, 'account_cleanup': True, 'live_source_and_focused_plan': True, 'dashboard_plan_summary': True, 'plan_history_filter_counts_and_restart': True, 'plan_theme_review_and_manual_task_loop': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--json-out', type=Path); args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-preparation-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'preparation.sqlite3')
        try: server.start(); result = asyncio.run(run(server))
        finally: server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
