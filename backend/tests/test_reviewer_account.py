import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.manage_database import create_reviewer_account
from app.models.entities import Account
from tests.test_ws_recovery import api


def test_provisioned_reviewer_has_regular_permissions_and_is_not_overwritten(api):
    client, session_factory = api
    password = 'synthetic-reviewer-password'
    with session_factory.begin() as db:
        create_reviewer_account(db, password)
        reviewer = db.scalar(select(Account).where(Account.username == 'admin'))
        assert reviewer.password_hash.startswith('pbkdf2_sha256$')
        assert password not in reviewer.password_hash

    with pytest.raises(IntegrityError):
        with session_factory.begin() as db:
            create_reviewer_account(db, 'another-synthetic-password')

    login = client.post('/api/auth/login', json={'username': 'admin', 'password': password})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert client.get('/api/auth/me', headers=headers).json()['is_admin'] is False
    assert client.get('/api/admin/overview', headers=headers).status_code == 403
