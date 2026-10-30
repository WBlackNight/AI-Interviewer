from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.models.entities import Interview
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source


def rows(client, user, **params):
    return client.get('/api/account/interviews?' + urlencode(params), headers=auth(user))


def make(factory, user, index, status='finished', position='java_backend', difficulty='mid'):
    sid = source(factory, user, index, status=status, position=position,
                 theme='MySQL' if position == 'java_backend' else 'Python基础')
    with factory() as db:
        db.get(Interview, sid).difficulty = difficulty
        db.commit()
    return sid


def test_combined_filters_and_scoped_status_counts(users):
    client, factory, a, b = users
    expected = make(factory, a, 1, 'running', difficulty='hard')
    make(factory, a, 2, 'finished', difficulty='hard')
    make(factory, a, 3, 'cancelled', difficulty='easy')
    make(factory, a, 4, 'created', position='python_backend')
    make(factory, b, 5, 'running', difficulty='hard')
    result = rows(client, a, status='running', position='java_backend', difficulty='hard').json()
    assert [item['interview_id'] for item in result['items']] == [expected]
    assert result['status_counts'] == {'created': 0, 'running': 1, 'finished': 1, 'cancelled': 0}
    assert result['position'] == 'java_backend' and result['difficulty'] == 'hard' and result['status'] == 'running'
    assert {item['id'] for item in result['positions']} == {'java_backend', 'python_backend'}
    assert rows(client, a).json()['total'] == 4 and rows(client, b).json()['total'] == 1


def test_empty_results_do_not_hide_other_owned_position_options(users):
    client, factory, a, b = users
    make(factory, a, 1)
    make(factory, b, 2, position='python_backend')
    result = rows(client, a, position='python_backend').json()
    assert result['items'] == [] and result['total'] == 0 and not result['has_more']
    assert result['status_counts'] == dict.fromkeys(['created', 'running', 'finished', 'cancelled'], 0)
    assert [item['id'] for item in result['positions']] == ['java_backend']


def test_filter_pagination_is_stable_and_does_not_return_answers(users):
    client, factory, a, _ = users
    expected = {make(factory, a, index) for index in range(1, 4)}
    make(factory, a, 4, 'cancelled')
    pages = [rows(client, a, status='finished', limit=1, offset=index).json() for index in range(3)]
    assert {page['items'][0]['interview_id'] for page in pages} == expected
    assert all(page['total'] == 3 for page in pages)
    assert [page['has_more'] for page in pages] == [True, True, False]
    assert rows(client, a, status='finished', limit=1, offset=1).json() == pages[1]
    assert 'private answer' not in str(pages) and 'private question' not in str(pages)


@pytest.mark.parametrize('params', [{'status': 'unknown'}, {'difficulty': 'normal'}, {'position': ''}, {'position': 'x' * 65}])
def test_invalid_filters_rejected_and_auth_required(users, params):
    client, _, a, _ = users
    assert rows(client, a, **params).status_code == 422
    assert client.get('/api/account/interviews?status=finished').status_code == 401


def test_reading_filters_does_not_modify_interview_state(users):
    client, factory, a, _ = users
    sid = make(factory, a, 1, 'created', difficulty='easy')
    before = rows(client, a).json()['items']
    assert rows(client, a, status='created', difficulty='easy').json()['items'] == before
    with factory() as db:
        assert db.scalar(select(Interview.status).where(Interview.id == sid)) == 'created'
