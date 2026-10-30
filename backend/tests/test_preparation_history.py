from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models.entities import Interview, PreparationPlan, PreparationPractice
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_preparation import create, patch, start, PATH
from tests.test_revision_tasks import source


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from app.api import preparation, routes
    monkeypatch.setattr(preparation, 'get_settings', lambda: routes.settings)


def records(client, user, key, **params):
    response = client.get(PATH + '/' + key + '/practices', headers=auth(user), params=params)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def test_history_auth_empty_plan_and_bounded_queries(users):
    client, _, a, b = users
    key = create(client, a)
    path = PATH + '/' + key + '/practices'
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth(b)).status_code == 404
    assert client.get(PATH + '/' + '0'*32 + '/practices', headers=auth(a)).status_code == 404
    result = records(client, a, key)
    assert result['items'] == [] and result['total'] == 0 and not result['has_more']
    assert result['status_counts'] == dict.fromkeys(['created', 'running', 'finished', 'cancelled'], 0)
    assert result['timezone'] == 'Asia/Shanghai' and result['plan']['id'] == key
    for params in [{'limit': 0}, {'limit': 21}, {'offset': -1}, {'offset': 1000001}, {'status': 'archived'}]:
        assert client.get(path, headers=auth(a), params=params).status_code == 422


def test_pagination_counts_shared_ownership_and_summary_privacy(users):
    client, factory, a, b = users
    key = create(client, a)
    statuses = ['created', 'running'] + ['finished']*6 + ['cancelled']*3
    ids = []
    for index, status in enumerate(statuses, 1):
        child = source(factory, a, index, status=status); ids.append(child)
        with factory() as db:
            db.add(PreparationPractice(plan_id=key, interview_id=child)); db.commit()
    foreign = source(factory, b, 99)
    unlinked = source(factory, a, 120)
    other_plan = create(client, a)
    other_child = source(factory, a, 130)
    with factory() as db:
        db.add_all([PreparationPractice(plan_id=key, interview_id=foreign), PreparationPractice(plan_id=other_plan, interview_id=other_child)])
        db.commit()
    first = records(client, a, key)
    second = records(client, a, key, offset=8)
    assert first['total'] == second['total'] == 11 and first['has_more'] and not second['has_more']
    assert [row['interview_id'] for row in first['items'] + second['items']] == ids[::-1]
    assert first['status_counts'] == {'created': 1, 'running': 1, 'finished': 6, 'cancelled': 3}
    filtered = records(client, a, key, status='finished', offset=2, limit=2)
    assert filtered['total'] == 6 and len(filtered['items']) == 2 and filtered['has_more']
    assert filtered['status_counts'] == first['status_counts']
    assert all(row['status'] == 'finished' and row['answer_count'] == 1 for row in filtered['items'])
    for row in first['items']:
        assert datetime.fromisoformat(row['saved_at']).utcoffset() == timezone.utc.utcoffset(None)
        assert not any(field in row for field in ['score', 'answer_text', 'content', 'resume_text', 'answer_points'])
    assert not any(value in str(first) for value in [foreign, unlinked, other_child, 'private answer', 'private question'])
    assert records(client, a, key, offset=1000000)['items'] == []
    assert records(client, a, key) == first


def test_archived_live_metadata_read_does_not_require_question_bank_or_mutate_state(users, monkeypatch):
    client, factory, a, _ = users
    key = create(client, a)
    child = start(client, a, key).json()['interview_id']
    patch(client, a, key, name='已调整的准备', target_date='2026-12-02', status='archived')
    with factory() as db:
        before_plan = (db.get(PreparationPlan, key).version, db.get(PreparationPlan, key).updated_at)
        before_interview = (db.get(Interview, child).status, db.get(Interview, child).plan)
    def forbidden(*args): raise AssertionError('read must not load question bank')
    monkeypatch.setattr('app.services.preparation.load_assets', forbidden)
    result = records(client, a, key)
    assert result['plan']['name'] == '已调整的准备' and result['plan']['status'] == 'archived'
    assert result['plan']['target_date'] == '2026-12-02' and result['items'][0]['interview_id'] == child
    assert records(client, a, key) == result
    with factory() as db:
        assert (db.get(PreparationPlan, key).version, db.get(PreparationPlan, key).updated_at) == before_plan
        assert (db.get(Interview, child).status, db.get(Interview, child).plan) == before_interview
        assert db.scalar(select(func.count()).select_from(Interview)) == 1


def test_deleting_interview_recounts_and_plan_removal_preserves_independent_report(users):
    client, _, a, _ = users
    key = create(client, a)
    first = start(client, a, key).json()['interview_id']
    assert client.post('/api/interview/' + first + '/cancel', headers={'X-Interview-Token': a['access_token']}).status_code == 200
    second = start(client, a, key).json()['interview_id']
    assert records(client, a, key)['status_counts'] == {'created': 1, 'running': 0, 'finished': 0, 'cancelled': 1}
    assert client.delete('/api/account/interviews/' + first, headers=auth(a)).status_code == 200
    result = records(client, a, key)
    assert result['total'] == 1 and result['status_counts']['cancelled'] == 0
    assert result['items'][0]['interview_id'] == second
    patch(client, a, key, status='archived')
    assert client.delete(PATH + '/' + key + '?expected_version=1', headers=auth(a)).status_code == 200
    assert client.get(PATH + '/' + key + '/practices', headers=auth(a)).status_code == 404
    assert client.get('/api/interview/' + second + '/report', headers={'X-Interview-Token': a['access_token']}).status_code == 200
