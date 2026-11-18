from datetime import datetime, timedelta

import pytest

from app.config import Settings
from app.models.entities import AccountProfile, Interview, QuestionScore, ResourceOwner
from app.services import admin
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api


@pytest.fixture
def managed(users, monkeypatch):
    client, factory, owner, ordinary = users
    config = Settings(_env_file=None, admin_account_ids=owner['account']['id'], llm_api_key=None)
    monkeypatch.setattr(admin, 'get_settings', lambda: config)
    from app.api import admin as routes
    monkeypatch.setattr(routes, 'get_settings', lambda: config)
    return client, factory, owner, ordinary, config


def test_admin_is_explicit_and_revocable_without_reissuing_session(managed):
    client, _, owner, ordinary, config = managed
    for path in ('overview', 'interviews', 'accounts', 'questions'):
        assert client.get('/api/admin/' + path).status_code == 401
        assert client.get('/api/admin/' + path, headers={**auth(ordinary), 'X-Admin': 'true'}).status_code == 403
        response = client.get('/api/admin/' + path, headers=auth(owner))
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/auth/me', headers=auth(owner)).json()['is_admin'] is True
    config.admin_account_ids = ''
    assert client.get('/api/admin/overview', headers=auth(owner)).status_code == 403
    assert client.get('/api/auth/me', headers=auth(owner)).json()['is_admin'] is False


def test_overview_uses_actual_counts_and_independent_started_completed_days(managed):
    client, factory, owner, ordinary, _ = managed
    local_today = datetime.now(admin.BEIJING).replace(hour=12, minute=0, second=0, microsecond=0).astimezone().replace(tzinfo=None)
    with factory() as db:
        for n, status in enumerate(('finished', 'running', 'created')):
            identity = str(n + 1) * 32
            db.add(Interview(id=identity, position='education', difficulty='mid', plan=[], status=status,
                             started_at=local_today - timedelta(days=1) if n == 0 else local_today if n == 1 else None,
                             ended_at=local_today if n == 0 else None))
            db.add(ResourceOwner(resource_kind='interview', resource_id=identity, account_id=owner['account']['id']))
        db.add_all([QuestionScore(interview_id='1' * 32, question_id='test', theme='教学设计', score=value,
                                  answer_text='PRIVATE ANSWER') for value in (5.0, 8.0)])
        db.commit()
    response = client.get('/api/admin/overview?days=7', headers=auth(owner))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['metrics']['interviews'] == 3
    assert data['metrics']['finished'] == 1
    assert data['metrics']['completion_rate'] == 33.3
    assert data['metrics']['answer_average'] == 6.5
    assert data['metrics']['scored_answers'] == 2
    assert data['metrics']['accounts'] == 2
    assert sum(row['count'] for row in data['coverage']) == data['metrics']['questions']
    assert sum(row['started'] for row in data['trend']) == 2
    assert sum(row['completed'] for row in data['trend']) == 1
    assert data['trend'][-1]['started'] == 1 and data['trend'][-2]['started'] == 1
    assert 'PRIVATE ANSWER' not in response.text
    page = client.get('/api/admin/interviews?status=finished&position=education', headers=auth(owner)).json()
    assert page['total'] == 1 and page['items'][0]['scored_answers'] == 2
    assert 'answer_text' not in page['items'][0]
    assert client.get('/api/admin/interviews?q=does-not-exist', headers=auth(owner)).json()['items'] == []


def test_account_lists_are_paginated_filtered_and_exclude_private_fields(managed):
    client, factory, owner, _, _ = managed
    with factory() as db:
        db.add(AccountProfile(account_id=owner['account']['id'], nickname='管理体验者', email='private@example.test'))
        db.commit()
    page = client.get('/api/admin/accounts?limit=1&offset=9999', headers=auth(owner)).json()
    assert page['total'] == 2 and page['offset'] == 1 and len(page['items']) == 1
    response = client.get('/api/admin/accounts?bound=bound&q=管理', headers=auth(owner))
    assert response.json()['total'] == 1
    row = response.json()['items'][0]
    assert row['email_bound'] and row['is_admin']
    assert not {'email', 'password_hash', 'access_token', 'avatar', 'bio'} & row.keys()
    assert 'private@example.test' not in response.text
    assert client.get('/api/admin/accounts?q=%25', headers=auth(owner)).json()['total'] == 0


def test_questions_use_active_assets_and_public_metadata_only(managed):
    client, _, owner, _, _ = managed
    result = client.get('/api/admin/questions?position=education&kind=knowledge&limit=10', headers=auth(owner)).json()
    assert result['total'] >= 20 and len(result['items']) == 10
    assert all(row['position'] == 'education' and not row['is_coding'] for row in result['items'])
    assert not {'answer_points', 'testcases'} & result['items'][0].keys()
    assert client.get('/api/admin/questions?q=__impossible__', headers=auth(owner)).json()['total'] == 0
    page = client.get('/admin', headers=auth(owner))
    assert page.status_code == 200
    assert page.headers['x-robots-tag'].startswith('noindex')


@pytest.mark.parametrize('path', ['overview?days=0', 'overview?days=91', 'interviews?limit=51',
                                  'accounts?offset=-1', 'interviews?status=unknown', 'questions?difficulty=invalid'])
def test_admin_rejects_unbounded_or_invalid_queries(managed, path):
    client, _, owner, _, _ = managed
    assert client.get('/api/admin/' + path, headers=auth(owner)).status_code == 422


def test_admin_configuration_never_accepts_usernames_or_tokens():
    with pytest.raises(ValueError):
        Settings(_env_file=None, admin_account_ids='admin')
    assert Settings(_env_file=None, admin_account_ids='a' * 32 + ',' + 'a' * 32).admin_account_ids == 'a' * 32
