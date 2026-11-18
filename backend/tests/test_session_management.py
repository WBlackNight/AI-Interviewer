from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api


def test_revoke_other_sessions_requires_password_and_preserves_current_and_other_account(users):
    client, _, first, second = users
    current = client.post('/api/auth/login', json={'username':'user_a','password':PASSWORD}).json()
    assert client.get('/api/account/security', headers=auth(current)).json()['active_sessions'] == 2
    path='/api/account/sessions/revoke-others'
    assert client.post(path, headers=auth(current), json={'current_password':'wrong-password-123'}).status_code == 403
    assert client.get('/api/auth/me', headers=auth(first)).status_code == 200
    result=client.post(path, headers=auth(current), json={'current_password':PASSWORD})
    assert result.status_code == 200 and result.json()['revoked'] == 1
    assert client.get('/api/auth/me', headers=auth(first)).status_code == 401
    assert client.get('/api/auth/me', headers=auth(current)).status_code == 200
    assert client.get('/api/auth/me', headers=auth(second)).status_code == 200
    assert client.get('/api/account/security', headers=auth(current)).json()['active_sessions'] == 1
    assert client.post(path, json={'current_password':PASSWORD}).status_code == 401
