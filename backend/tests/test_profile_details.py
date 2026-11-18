import pytest

from app.models.entities import AccountDetails
from tests.test_accounts import users, auth, PASSWORD, resource
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source


def test_optional_details_save_partial_clear_conflict_and_account_isolation(users):
    client, factory, a, b = users
    original = client.get('/api/auth/me', headers=auth(a)).json()
    assert original['age'] is None and original['gender'] is None and original['bio'] == ''
    saved = client.patch('/api/account/profile', headers=auth(a), json={
        'nickname': '新昵称', 'gender': 'female', 'age': 26, 'bio': '  准备英语面试  ', 'expected_version': 0})
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data['age'] == 26 and data['gender'] == 'female' and data['bio'] == '准备英语面试'
    assert data['profile_version'] == 1
    assert client.get('/api/auth/me', headers=auth(b)).json()['age'] is None
    assert client.patch('/api/account/profile', headers=auth(a), json={'age': 27, 'expected_version': 0}).status_code == 409
    unchanged = client.patch('/api/account/profile', headers=auth(a), json={'age': 26, 'expected_version': 1})
    assert unchanged.json()['profile_version'] == 1
    cleared = client.patch('/api/account/profile', headers=auth(a),
        json={'age': None, 'gender': None, 'bio': '', 'expected_version': 1}).json()
    assert cleared['nickname'] == '新昵称' and cleared['age'] is None
    assert cleared['profile_version'] == 2
    # 旧版只修改昵称的调用继续保留其余资料。
    client.patch('/api/account/profile', headers=auth(a), json={'age': 30})
    assert client.patch('/api/account/profile', headers=auth(a), json={'nickname': '更新昵称'}).json()['age'] == 30
    sid = source(factory, a)
    assert 'gender' not in client.get(f'/api/interview/{sid}/report', headers=resource(a)).text
    assert client.request('DELETE', '/api/account', headers=auth(a), json={'password': PASSWORD}).status_code == 200
    with factory() as db:
        assert db.get(AccountDetails, a['account']['id']) is None


@pytest.mark.parametrize('payload', [
    {'age': 0}, {'age': 121}, {'age': 1.5}, {'age': True}, {'age': '20'},
    {'gender': 'invalid'}, {'bio': '字' * 161}, {'nickname': None}, {},
])
def test_profile_details_reject_invalid_values(users, payload):
    client, _, a, _ = users
    assert client.patch('/api/account/profile', headers=auth(a), json=payload).status_code == 422
    assert client.patch('/api/account/profile', json=payload).status_code == 401
