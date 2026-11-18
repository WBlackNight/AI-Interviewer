from sqlalchemy import func, select

from app.config import Settings
from app.models.forum import ForumIdentityChange
from app.services import admin, forum
from tests.test_accounts import PASSWORD, auth, users
from tests.test_ws_recovery import api

BASE = '/api/forum'


def identity(client, user, value='student'):
    result = client.put(BASE + '/identity', headers=auth(user), json={'identity': value})
    assert result.status_code == 200, result.text
    return result.json()


def publish(client, user, title='前端面试复盘', body='先交代约束，再介绍取舍。📌'):
    result = client.post(BASE + '/posts', headers=auth(user), json={'title': title, 'body': body})
    assert result.status_code == 201, result.text
    return result.json()['id']


def test_revoked_session_can_read_public_forum_but_cannot_act(users):
    client, _, author, _ = users
    identity(client, author)
    post = publish(client, author)
    headers = auth(author)
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    assert client.get(BASE + '/context', headers=headers).json()['viewer'] is None
    assert client.get(BASE + '/posts/' + post, headers=headers).status_code == 200
    assert client.get(BASE + '/posts?filter=saved', headers=headers).status_code == 401
    assert client.put(BASE + '/posts/' + post + '/like', headers=headers).status_code == 401


def test_public_feed_and_identity_snapshots(users):
    client, factory, author, other = users
    assert client.get('/forum').status_code == 200
    assert client.get(BASE + '/posts').json() == {'items': [], 'next_offset': None}
    payload = {'title': '初次发帖', 'body': '复盘建议'}
    assert client.post(BASE + '/posts', json=payload).status_code == 401
    assert client.post(BASE + '/posts', headers=auth(author), json=payload).status_code == 409
    assert client.get(BASE + '/users/' + other['account']['id']).status_code == 404
    assert identity(client, author)['identity'] == 'student'
    post = publish(client, author, body='<script>plain text</script>🙂')
    identity(client, author, 'employee')
    identity(client, author, 'employee')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ForumIdentityChange)) == 2
    reply = client.post(BASE + '/posts/' + post + '/comments', headers=auth(author), json={'body': '我补充一点 💡'})
    assert reply.status_code == 201, reply.text
    data = client.get(BASE + '/posts/' + post).json()
    assert data['identity'] == 'student' and data['body'] == '<script>plain text</script>🙂'
    replies = client.get(BASE + '/posts/' + post + '/comments').json()['items']
    assert replies[0]['identity'] == 'employee' and replies[0]['body'].endswith('💡')
    person = client.get(BASE + '/users/' + author['account']['id']).json()
    assert person['identity'] == 'employee' and person['post_count'] == 1 and not person['is_self']
    assert 'email' not in str(person) and 'password_hash' not in str(person)
    assert person['recent_posts'][0]['id'] == post


def test_rank_search_featured_and_private_bookmarks(users, monkeypatch):
    client, _, a, b = users
    monkeypatch.setattr(forum, 'get_settings', lambda: Settings(_env_file=None, forum_featured_likes=2))
    from app.api import forum as routes
    monkeypatch.setattr(routes, 'get_settings', forum.get_settings)
    identity(client, a)
    older = publish(client, a, title='React 复盘 100%')
    newer = publish(client, a, title='另一个练习')
    base = BASE + '/posts/' + older
    for user in (a, b, a):
        result = client.put(base + '/like', headers=auth(user))
        assert result.status_code == 200, result.text
    assert result.json()['likes'] == 2 and result.json()['featured']
    assert client.get(BASE + '/posts?sort=latest').json()['items'][0]['id'] == newer
    assert client.get(BASE + '/posts?sort=rank').json()['items'][0]['id'] == older
    assert client.get(BASE + '/posts?filter=featured').json()['items'][0]['id'] == older
    for _ in range(2):
        assert client.put(base + '/bookmark', headers=auth(a)).json()['saved']
    assert len(client.get(BASE + '/posts?filter=saved', headers=auth(a)).json()['items']) == 1
    assert not client.get(BASE + '/posts?filter=saved', headers=auth(b)).json()['items']
    assert client.get(BASE + '/posts?filter=saved').status_code == 401
    assert client.get(BASE + '/users/' + a['account']['id']).json()['saved_count'] == 1
    assert not client.delete(base + '/bookmark', headers=auth(a)).json()['saved']
    assert not client.delete(base + '/like', headers=auth(b)).json()['featured']
    for term, count in [('react', 1), ('学生', 2), ('%', 1), ('user_a', 2)]:
        data = client.get(BASE + '/search', params={'q': term}).json()
        assert len(data['posts']['items']) == count, data
    assert client.get(BASE + '/search', params={'q': '学生'}).json()['users']['items'][0]['id'] == a['account']['id']
    assert client.get(BASE + '/search', params={'q': '_'}).json()['posts']['items']
    assert client.get(BASE + '/posts?limit=1').json()['next_offset'] == 1


def test_reports_quota_and_admin_moderation(users, monkeypatch):
    client, _, a, b = users
    monkeypatch.setattr(admin, 'get_settings', lambda: Settings(_env_file=None,
        admin_account_ids=a['account']['id'], admin_viewer_account_ids=b['account']['id']))
    identity(client, a)
    post_ids = [publish(client, a, title='讨论 ' + str(i)) for i in range(6)]
    route = BASE + '/posts/' + post_ids[0]
    comment = client.post(route + '/comments', headers=auth(a), json={'body': '待审核回复'}).json()['id']
    wrong_target = BASE + '/posts/' + post_ids[1] + '/comments/' + comment + '/reports'
    assert client.post(wrong_target, headers=auth(b), json={'reason': 'abuse'}).status_code == 404
    report_route = route + '/comments/' + comment + '/reports'
    assert client.post(report_route, json={'reason': 'abuse'}).status_code == 401
    first = client.post(report_route, headers=auth(b), json={'reason': 'abuse'}).json()
    duplicate = client.post(report_route, headers=auth(b), json={'reason': 'spam'}).json()
    assert duplicate == {**first, 'duplicate': True}
    assert client.get(BASE + '/moderation/reports', headers=auth(b)).status_code == 403
    queue = client.get(BASE + '/moderation/reports', headers=auth(a)).json()
    assert len(queue['items']) == 1 and queue['items'][0]['reason'] == 'abuse'
    action = BASE + '/moderation/reports/' + first['id']
    assert client.get(action, headers=auth(a)).json()['body'] == '待审核回复'
    decision = {'decision': 'hide', 'note': '已核对回复内容'}
    assert client.patch(action, headers=auth(b), json=decision).status_code == 403
    assert client.patch(action, headers=auth(a), json=decision).json()['status'] == 'actioned'
    assert client.patch(action, headers=auth(a), json=decision).status_code == 409
    assert not client.get(route + '/comments').json()['items']
    assert client.get(route).json()['comments'] == 0
    for post in post_ids[:4]:
        report = client.post(BASE + '/posts/' + post + '/reports', headers=auth(b), json={'reason': 'spam'})
        assert report.status_code == 200
        if post == post_ids[0]:
            assert client.patch(BASE + '/moderation/reports/' + report.json()['id'],
                                headers=auth(a), json=decision).status_code == 200
    assert client.get(route).status_code == 404
    assert not client.get(BASE + '/search', params={'q': '讨论 0'}).json()['posts']['items']
    limited = client.post(BASE + '/posts/' + post_ids[5] + '/reports', headers=auth(b), json={'reason': 'spam'})
    assert limited.status_code == 429


def test_invalid_content_and_account_removal(users):
    client, _, a, b = users
    identity(client, a)
    identity(client, b, 'employee')
    for text in ('   ', '刷 单 返 利', '乱码\x00'):
        assert client.post(BASE + '/posts', headers=auth(a), json={'title': '问题', 'body': text}).status_code == 422
    post = publish(client, a)
    route = BASE + '/posts/' + post
    assert client.post(route + '/comments', headers=auth(b), json={'body': '回帖'}).status_code == 201
    assert client.put(route + '/bookmark', headers=auth(b)).status_code == 200
    assert client.post(route + '/reports', headers=auth(b), json={'reason': 'other'}).status_code == 200
    result = client.request('DELETE', '/api/account', headers=auth(a), json={'password': PASSWORD})
    assert result.status_code == 200, result.text
    assert client.get(route).status_code == 404
    assert not client.get(BASE + '/posts?filter=saved', headers=auth(b)).json()['items']
