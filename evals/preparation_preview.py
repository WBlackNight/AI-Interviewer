"""可选的合成计划记录队列：只通过隔离Server的API/WS生成，不改开发库。"""
from datetime import datetime, timedelta, timezone

from smoke_e2e import request
from question_marks_smoke import call
from practice_smoke import complete


async def seed_plan_history(server):
    account = request(server.base, '/api/auth/login', {'username': 'ui_review_demo', 'password': 'local-demo-password-2026'})
    headers = {'Authorization': 'Bearer ' + account['access_token']}
    target = datetime.now(timezone(timedelta(hours=8))).date() + timedelta(days=7)
    key = call(server, '/api/account/preparation-plans', headers, 'POST', {
        'name': '数据库准备 · 练习记录演示', 'position': 'java_backend', 'themes': ['MySQL'],
        'difficulty': 'mid', 'target_date': target.isoformat()})['id']
    base = '/api/account/preparation-plans/' + key
    first = call(server, base + '/practice', headers, 'POST', {'expected_version': 0})
    await complete(server, {**first, 'access_token': account['access_token']}, ['MySQL'])
    for _ in range(8):
        child = call(server, base + '/practice', headers, 'POST', {'expected_version': 0})
        request(server.base, '/api/interview/' + child['interview_id'] + '/cancel', {}, {'X-Interview-Token': account['access_token']})
    call(server, base + '/practice', headers, 'POST', {'expected_version': 0})
    history = call(server, base + '/practices', headers)
    assert history['total'] == 10 and history['has_more']
    assert history['status_counts'] == {'created': 1, 'running': 0, 'finished': 1, 'cancelled': 8}
    return 'http://localhost:3000/plan-history?plan_id=' + key
