import pytest

from app.models.entities import PreparationPlan, PreparationPractice
from tests.test_accounts import users, auth, resource
from tests.test_ws_recovery import api
from tests.test_preparation import create, patch, PATH
from tests.test_score_origin_review import add_session, record


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from app.api import preparation, routes
    monkeypatch.setattr(preparation, 'get_settings', lambda: routes.settings)


def attach(factory, key, child):
    with factory() as db:
        db.add(PreparationPractice(plan_id=key, interview_id=child)); db.commit()


def review(client, user, key, **params):
    response = client.get(PATH + '/' + key + '/review', headers=auth(user), params=params)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def test_plan_review_scopes_facets_owner_and_position_and_matches_report_math(users):
    client, factory, a, b = users
    key, other_plan = create(client, a), create(client, a)
    own = add_session(factory, a['account']['id'], 1, [record('a', 0), record('a#p1', 10, source='llm', cached=True),
        record('a#p2', 10, source='heuristic_fallback'), record('b', 10), record('c', 3, theme='Redis')])
    attach(factory, key, own)
    foreign = add_session(factory, b['account']['id'], 99, [record(theme='foreign-private')]); attach(factory, key, foreign)
    add_session(factory, a['account']['id'], 100, [record(theme='unlinked-private')])
    other = add_session(factory, a['account']['id'], 101, [record(theme='other-plan-private')]); attach(factory, other_plan, other)
    wrong_position = add_session(factory, a['account']['id'], 102, [record(theme='Python基础')], position='python_backend'); attach(factory, key, wrong_position)
    result = review(client, a, key)
    assert result['positions'] == [{'id': 'java_backend', 'display_name': 'Java 后端', 'themes': ['MySQL', 'Redis']}]
    assert result['preparation_plan_id'] == key and result['theme'] == 'MySQL' and result['completed_only']
    row = result['items'][0]
    assert result['total'] == 1 and row['interview_id'] == own and row['score'] == 8.3
    assert row['question_count'] == 2 and row['answer_count'] == 4
    assert row['scoring_sources'] == {'heuristic': 2, 'llm': 1, 'heuristic_fallback': 1}
    assert sum(profile['cached_count'] for profile in row['scoring_profiles']) == 1
    report = client.get('/api/interview/' + own + '/report', headers=resource(a)).json()
    assert row['score'] == report['theme_avg']['MySQL']
    assert not any(value in str(result) for value in ['private question', 'private answer', foreign, wrong_position, other, 'unlinked-private'])
    assert review(client, a, key, theme='Redis')['items'][0]['score'] == 3
    assert client.get(PATH + '/' + key + '/review').status_code == 401
    assert client.get(PATH + '/' + key + '/review', headers=auth(b)).status_code == 404


def test_plan_review_paginates_finished_only_and_keeps_account_repeat_definition(users, monkeypatch):
    client, factory, a, _ = users
    key = create(client, a)
    add_session(factory, a['account']['id'], 0, [record()])  # 同账户、计划外的先前同版本题。
    ids = []
    for index in range(1, 8):
        child = add_session(factory, a['account']['id'], index, [record()], legacy=index == 7)
        attach(factory, key, child); ids.append(child)
    for index, status in [(20, 'running'), (21, 'cancelled'), (22, 'created')]:
        attach(factory, key, add_session(factory, a['account']['id'], index, [record(theme='unfinished')], status=status))
    def forbidden(*args): raise AssertionError('read must not load bank or call model')
    monkeypatch.setattr('app.services.preparation.load_assets', forbidden)
    first, second = review(client, a, key, limit=4), review(client, a, key, offset=4, limit=4)
    assert first['total'] == 7 and first['has_more'] and not second['has_more']
    assert [row['interview_id'] for row in first['items'] + second['items']] == ids[::-1]
    assert first['items'][0]['unknown_question_version_count'] == 1
    assert first['items'][0]['scoring_sources'] == {'unknown': 1}
    assert first['items'][1]['repeat_question_count'] == 1
    assert first['positions'][0]['themes'] == ['MySQL']
    assert review(client, a, key, theme='missing')['total'] == 0
    assert review(client, a, key, offset=1000000)['items'] == []
    for params in [{'limit': 11}, {'offset': -1}, {'offset': 1000001}, {'theme': ''}, {'theme': 'x'*65}]:
        assert client.get(PATH + '/' + key + '/review', headers=auth(a), params=params).status_code == 422


def test_plan_review_task_loop_is_explicit_idempotent_and_lifecycle_independent(users):
    client, factory, a, _ = users
    key = create(client, a)
    assert review(client, a, key)['items'] == []
    child = add_session(factory, a['account']['id'], 1, [record(value=3)], legacy=True); attach(factory, key, child)
    before = review(client, a, key)
    assert client.get('/api/account/revision-tasks', headers=auth(a)).json()['total'] == 0
    endpoint = '/api/account/interviews/' + child + '/revision-tasks'
    result = client.post(endpoint, headers=auth(a)).json()
    assert result['added'] == 1
    task = result['items'][0]
    assert client.patch('/api/account/revision-tasks/' + task['id'], headers=auth(a), json={'status': 'done'}).status_code == 200
    duplicate = client.post(endpoint, headers=auth(a)).json()
    assert duplicate['added'] == 0 and duplicate['existing'] == 1 and duplicate['items'][0]['status'] == 'done'
    assert review(client, a, key) == before
    with factory() as db: assert db.get(PreparationPlan, key).version == 0
    patch(client, a, key, status='archived')
    assert review(client, a, key)['items'] == before['items']
    assert client.delete('/api/account/interviews/' + child, headers=auth(a)).status_code == 200
    assert review(client, a, key)['items'] == []
    assert client.get('/api/account/revision-tasks', headers=auth(a)).json()['total'] == 0
    assert client.delete(PATH + '/' + key + '?expected_version=1', headers=auth(a)).status_code == 200
    assert client.get(PATH + '/' + key + '/review', headers=auth(a)).status_code == 404
