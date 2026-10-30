from datetime import date

import pytest
from sqlalchemy import event, func, select

from app.models.entities import Interview, PreparationPlan, PreparationPractice, ResourceOwner
from app.rag.question_bank import QuestionBank
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api

PATH = '/api/account/preparation-plans'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from app.api import preparation, routes
    monkeypatch.setattr(preparation, 'get_settings', lambda: routes.settings)


def create(client, user, **changes):
    result = client.post(PATH, headers=auth(user), json={'name': '准备数据库', 'position': 'java_backend',
        'themes': ['MySQL'], 'difficulty': 'mid', **changes})
    assert result.status_code == 200, result.text
    return result.json()['id']


def listing(client, user, **params):
    response = client.get(PATH, headers=auth(user), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def start(client, user, key, version=0):
    return client.post(PATH + '/' + key + '/practice', headers=auth(user), json={'expected_version': version})


def patch(client, user, key, version=0, **changes):
    return client.patch(PATH + '/' + key, headers=auth(user), json={'expected_version': version, **changes})


def test_create_is_private_metadata_only_and_scopes_all_operations(users):
    client, factory, a, b = users
    key = create(client, a, name='  面试准备  ', target_date='2026-12-01')
    row = listing(client, a)['items'][0]
    assert row['name'] == '面试准备' and row['version'] == 0 and row['target_date'] == '2026-12-01'
    assert row['available'] and row['finished_count'] == 0 and row['latest_practice'] is None
    assert listing(client, b)['total'] == 0 and client.get(PATH).status_code == 401
    assert client.get(PATH, headers=auth(a)).headers['cache-control'] == 'no-store'
    assert patch(client, b, key, name='other').status_code == 404
    assert start(client, b, key).status_code == 404
    assert client.delete(PATH + '/' + key + '?expected_version=0', headers=auth(b)).status_code == 404
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 0
        assert db.scalar(select(func.count()).select_from(PreparationPractice)) == 0
    assert not any(field in str(row) for field in ['answer_text', 'answer_points', 'resume_text'])


def test_strict_inputs_dates_fixed_scope_and_empty_updates(users):
    client, _, a, _ = users
    for changes in [{'name': ' '}, {'name': '字'*81}, {'position': 'missing'}, {'themes': []},
                    {'themes': ['MySQL', 'MySQL']}, {'themes': ['算法与编码']},
                    {'target_date': 20261201}, {'target_date': '2026-02-30'}, {'target_date': '2026-1-1'},
                    {'target_date': '2101-01-01'}, {'difficulty': 'normal'}, {'extra': 'private-value'}]:
        body = {'name': 'valid', 'position': 'java_backend', 'themes': ['MySQL'], **changes}
        assert client.post(PATH, headers=auth(a), json=body).status_code == 422, changes
    key = create(client, a)
    assert client.patch(PATH + '/' + key, headers=auth(a), json={'expected_version': 0}).status_code == 422
    assert patch(client, a, key, themes=['Redis']).status_code == 422
    assert patch(client, a, key, name=None).status_code == 422
    assert client.get(PATH + '?limit=21', headers=auth(a)).status_code == 422
    assert client.get(PATH + '?status=done', headers=auth(a)).status_code == 422


def test_version_date_clear_noop_and_archive_restore(users):
    client, _, a, _ = users
    key = create(client, a, target_date='2026-10-01')
    assert patch(client, a, key, name='新名称', target_date=None).json()['version'] == 1
    before = listing(client, a)['items'][0]
    assert before['target_date'] is None
    assert patch(client, a, key, 1, name='新名称').json()['version'] == 1
    assert listing(client, a)['items'][0] == before
    assert patch(client, a, key, name='stale').status_code == 409
    assert patch(client, a, key, 1, status='archived').json()['version'] == 2
    assert start(client, a, key, 2).status_code == 409
    assert patch(client, a, key, 2, status='active').json()['version'] == 3
    assert start(client, a, key, 0).status_code == 409


def test_counts_position_pagination_and_beijing_target_dates(users, monkeypatch):
    from app.services import preparation
    monkeypatch.setattr(preparation, 'revision_today', lambda: date(2026, 10, 26))
    client, _, a, _ = users
    keys = [create(client, a, name=str(i), target_date='2026-10-25' if i < 2 else '2026-10-26') for i in range(9)]
    create(client, a, position='python_backend', themes=['Python基础'], target_date=None)
    patch(client, a, keys[0], status='archived')
    result = listing(client, a, status='active', position='java_backend')
    assert result['counts'] == {'active': 8, 'archived': 1, 'past_target': 1}
    assert len(result['positions']) == 2 and result['timezone'] == 'Asia/Shanghai'
    first, second = listing(client, a, limit=8), listing(client, a, offset=8, limit=8)
    assert first['has_more'] and not second['has_more']
    assert len({row['id'] for row in first['items'] + second['items']}) == 10


def test_created_running_reuse_and_owned_scope(users):
    client, factory, a, _ = users
    key = create(client, a, themes=['MySQL', 'Redis'], difficulty='hard')
    first = start(client, a, key).json()
    assert first['account_owned'] and first['access_token'] is None and not first['reused']
    assert {item['theme'] for item in first['plan']} == {'MySQL', 'Redis'}
    assert all(item['difficulty'] == 'hard' and not item['include_coding'] and item['question_count'] <= 2 for item in first['plan'])
    assert start(client, a, key).json()['interview_id'] == first['interview_id']
    with factory() as db:
        row = db.get(Interview, first['interview_id']); row.status = 'running'; db.commit()
        assert row.resume_id is None and row.user_id is None
        assert db.get(ResourceOwner, ('interview', row.id)).account_id == a['account']['id']
    assert start(client, a, key).json()['reused']
    with factory() as db: assert db.scalar(select(func.count()).select_from(PreparationPractice)) == 1


def test_finished_count_cancelled_exclusion_and_manual_metadata_stay_independent(users):
    client, factory, a, _ = users
    key = create(client, a)
    first = start(client, a, key).json()['interview_id']
    with factory() as db: db.get(Interview, first).status = 'finished'; db.commit()
    second = start(client, a, key).json()['interview_id']
    assert first != second
    with factory() as db: db.get(Interview, second).status = 'cancelled'; db.commit()
    row = listing(client, a)['items'][0]
    assert row['finished_count'] == 1 and row['version'] == 0 and row['status'] == 'active'
    assert row['latest_practice'] == {'interview_id': second, 'status': 'cancelled'}
    third = start(client, a, key).json()['interview_id']
    assert third not in [first, second]


def test_asset_change_marks_unavailable_but_pending_practice_is_reused(users, monkeypatch):
    from app.services import preparation
    from app.api import routes
    client, _, a, _ = users
    first, second = create(client, a), create(client, a)
    child = start(client, a, first).json()['interview_id']
    trees, _ = preparation.load_assets(routes.settings)
    monkeypatch.setattr(preparation, 'load_assets', lambda settings: (trees, QuestionBank([])))
    assert not listing(client, a)['items'][0]['available']
    assert start(client, a, second).status_code == 422
    assert start(client, a, first).json()['interview_id'] == child


def test_association_failure_rolls_back_interview_owner_and_link(users):
    client, factory, a, _ = users
    key = create(client, a)
    engine = factory.kw['bind']
    def fail(connection, cursor, statement, *args):
        if statement.startswith('INSERT INTO preparation_practice'): raise RuntimeError('synthetic-failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic-failure'): start(client, a, key)
    finally: event.remove(engine, 'before_cursor_execute', fail)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 0
        assert db.scalar(select(func.count()).select_from(ResourceOwner)) == 0
        assert db.get(PreparationPlan, key) is not None


def test_plan_interview_and_account_deletion_have_independent_lifecycles(users):
    client, factory, a, b = users
    key = create(client, a); other = create(client, b)
    child = start(client, a, key).json()['interview_id']
    assert client.delete(PATH + '/' + key + '?expected_version=0', headers=auth(a)).status_code == 409
    assert client.delete('/api/account/interviews/' + child, headers=auth(a)).status_code == 200
    assert listing(client, a)['items'][0]['latest_practice'] is None
    kept = start(client, a, key).json()['interview_id']
    patch(client, a, key, status='archived')
    assert client.delete(PATH + '/' + key + '?expected_version=0', headers=auth(a)).status_code == 409
    assert client.delete(PATH + '/' + key + '?expected_version=1', headers=auth(a)).json()['deleted']
    with factory() as db: assert db.get(Interview, kept) is not None
    create(client, a)
    assert client.request('DELETE', '/api/account', headers=auth(a), json={'password': PASSWORD}).status_code == 200
    assert listing(client, b)['items'][0]['id'] == other
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PreparationPlan)) == 1
        assert db.scalar(select(func.count()).select_from(PreparationPractice)) == 0


def test_capacity_can_be_released_by_removing_archived_plan(users):
    from app.services.accounts import now_utc
    client, factory, a, _ = users
    key = create(client, a)
    with factory() as db:
        db.add_all([PreparationPlan(account_id=a['account']['id'], name=str(i), position='java_backend', themes=['MySQL'],
            difficulty='mid', status='active', version=0, created_at=now_utc(), updated_at=now_utc()) for i in range(49)])
        db.commit()
    assert client.post(PATH, headers=auth(a), json={'name': 'over', 'position': 'java_backend', 'themes': ['MySQL']}).status_code == 409
    patch(client, a, key, status='archived')
    assert client.delete(PATH + '/' + key + '?expected_version=1', headers=auth(a)).status_code == 200
    assert create(client, a)


def source_path(interview_id):
    return PATH + '/source/' + interview_id


def test_source_is_owner_only_live_metadata_outside_report_and_export(users):
    client, _, a, b = users
    key = create(client, a, name='private-plan-unique', target_date='2099-12-31')
    child = start(client, a, key).json()['interview_id']
    path = source_path(child)
    before = client.get('/api/interview/' + child + '/report', headers={'X-Interview-Token': a['access_token']}).json()
    result = client.get(path, headers=auth(a))
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['source'] == {'id': key, 'name': 'private-plan-unique', 'status': 'active', 'target_date': '2099-12-31'}
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'X-Interview-Token': a['access_token']}).status_code == 401
    assert client.get(path, headers=auth(b)).status_code == 404
    assert client.get(source_path('0' * 32), headers=auth(a)).status_code == 404
    assert patch(client, a, key, name='renamed-private-plan', status='archived', target_date=None).status_code == 200
    current = client.get(path, headers=auth(a)).json()['source']
    assert current['name'] == 'renamed-private-plan' and current['status'] == 'archived' and current['target_date'] is None
    after = client.get('/api/interview/' + child + '/report', headers={'X-Interview-Token': a['access_token']}).json()
    assert after == before
    for format in ['json', 'markdown']:
        export = client.get('/api/interview/' + child + '/report/export?format=' + format, headers={'X-Interview-Token': a['access_token']})
        assert export.status_code == 200
        assert not any(value in export.text for value in ['private-plan', '2099-12-31', key])


def test_focus_finds_archived_plan_outside_first_page_without_leaking_or_truncating_counts(users):
    client, _, a, b = users
    key = create(client, a)
    for index in range(9): create(client, a, name='newer-' + str(index))
    patch(client, a, key, status='archived')
    assert key not in {row['id'] for row in listing(client, a)['items']}
    result = listing(client, a, plan_id=key)
    assert result['total'] == 1 and result['items'][0]['id'] == key and result['items'][0]['status'] == 'archived'
    assert result['counts'] == {'active': 9, 'archived': 1, 'past_target': 0}
    assert listing(client, a, plan_id=key, status='active')['items'] == []
    assert listing(client, b, plan_id=key)['items'] == []
    assert client.get(PATH, headers=auth(a), params={'plan_id': 'invalid'}).status_code == 422
    assert listing(client, a, plan_id=key) == result


def test_source_disappears_after_plan_removal_but_report_survives_and_interview_delete_is_404(users):
    client, _, a, _ = users
    key = create(client, a)
    child = start(client, a, key).json()['interview_id']
    patch(client, a, key, status='archived')
    assert client.delete(PATH + '/' + key + '?expected_version=1', headers=auth(a)).status_code == 200
    assert client.get(source_path(child), headers=auth(a)).json() == {'source': None}
    assert client.get('/api/interview/' + child + '/report', headers={'X-Interview-Token': a['access_token']}).status_code == 200
    assert client.delete('/api/account/interviews/' + child, headers=auth(a)).status_code == 200
    assert client.get(source_path(child), headers=auth(a)).status_code == 404


def test_dashboard_plan_summary_zeroes_bounds_date_order_and_account_isolation(users, monkeypatch):
    client, factory, a, b = users
    monkeypatch.setattr('app.services.dashboard.revision_today', lambda: date(2026, 10, 27))
    def summary(user): return client.get('/api/account/dashboard', headers=auth(user)).json()['preparation']
    assert summary(a) == {'counts': {'active': 0, 'archived': 0, 'past_target': 0}, 'items': [], 'limit': 3}
    unscheduled = create(client, a, name='no-date')
    future = create(client, a, name='future', target_date='2026-11-01')
    today = create(client, a, name='today', target_date='2026-10-27')
    overdue = create(client, a, name='past', target_date='2026-10-26')
    archived = create(client, a, name='archived', target_date='2020-01-01')
    patch(client, a, archived, status='archived')
    other = create(client, b, name='other-secret', target_date='2000-01-01')
    result = summary(a)
    assert result['counts'] == {'active': 4, 'archived': 1, 'past_target': 1}
    assert [row['id'] for row in result['items']] == [overdue, today, future]
    assert not any(value in str(result) for value in [other, 'other-secret', unscheduled, archived])
    patch(client, a, overdue, status='archived')
    assert [row['id'] for row in summary(a)['items']] == [today, future, unscheduled]
    assert summary(b)['counts'] == {'active': 1, 'archived': 0, 'past_target': 1}
    assert summary(a) == summary(a)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 0
        assert db.get(PreparationPlan, unscheduled).version == 0
