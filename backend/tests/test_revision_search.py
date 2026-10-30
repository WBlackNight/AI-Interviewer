from urllib.parse import urlencode

import pytest

from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source, add


def board(client, user, **params):
    return client.get('/api/account/revision-tasks?' + urlencode(params), headers=auth(user))


def task(client, factory, user, index, theme='MySQL', note=None):
    sid = source(factory, user, index, theme=theme)
    item = add(client, user, sid).json()['items'][0]
    if note is not None:
        assert client.put('/api/account/revision-tasks/' + item['id'] + '/note', headers=auth(user),
                          json={'content': note, 'expected_version': 0}).status_code == 200
    return item


def test_search_theme_note_trim_case_and_missing(users):
    client, factory, a, _ = users
    first = task(client, factory, a, 1, note='范围查询需要解释磁盘访问')
    second = task(client, factory, a, 2, 'Redis', '缓存过期')
    assert board(client, a, q=' mysql ').json()['query'] == 'mysql'
    assert board(client, a, q='mysql').json()['items'][0]['id'] == first['id']
    assert board(client, a, q='磁盘访问').json()['items'][0]['id'] == first['id']
    assert board(client, a, q='缓存').json()['items'][0]['id'] == second['id']
    assert board(client, a, q='不存在的检索词').json()['total'] == 0
    assert board(client, a, q='  ').json()['total'] == 2


@pytest.mark.parametrize('literal', ['%', '_', '/', '\\', "' OR 1=1 --"])
def test_search_treats_wildcards_and_sql_as_literal_text(users, literal):
    client, factory, a, _ = users
    expected = task(client, factory, a, 1, note='只匹配这里：' + literal)
    task(client, factory, a, 2, note='普通笔记')
    result = board(client, a, q=literal).json()
    assert result['total'] == 1 and result['items'][0]['id'] == expected['id']


def test_note_filters_include_whitespace_but_not_missing_or_cleared(users):
    client, factory, a, _ = users
    saved = task(client, factory, a, 1, note='文字')
    blank = task(client, factory, a, 2, note='  ')
    absent = task(client, factory, a, 3)
    cleared = task(client, factory, a, 4, note='曾经保存')
    client.put('/api/account/revision-tasks/' + cleared['id'] + '/note', headers=auth(a),
               json={'content': '', 'expected_version': 1})
    assert {item['id'] for item in board(client, a, note_filter='with').json()['items']} == {saved['id'], blank['id']}
    assert {item['id'] for item in board(client, a, note_filter='without').json()['items']} == {absent['id'], cleared['id']}
    assert board(client, a, q='文字', note_filter='without').json()['total'] == 0


def test_search_is_scoped_before_counts_and_combines_with_status_dates(users):
    client, factory, a, b = users
    first = task(client, factory, a, 1, note='共同关键词')
    second = task(client, factory, a, 2, note='共同关键词')
    task(client, factory, a, 3, 'Redis', note='其他内容')
    task(client, factory, b, 4, note='共同关键词，不能泄漏')
    today = board(client, a).json()['today']
    client.patch('/api/account/revision-tasks/' + first['id'], headers=auth(a), json={'due_date': today})
    client.patch('/api/account/revision-tasks/' + second['id'], headers=auth(a), json={'status': 'done'})
    result = board(client, a, q='共同', note_filter='with', status='todo', due='today', position='java_backend').json()
    assert [item['id'] for item in result['items']] == [first['id']]
    assert result['counts'] == {'todo': 1, 'done': 1}
    assert result['date_counts'] == {'today': 1, 'overdue': 0, 'upcoming': 0, 'unscheduled': 0}
    assert board(client, a, q='不能泄漏').json()['total'] == 0
    assert board(client, b, q='共同').json()['total'] == 1
    assert board(client, a, q='共同', position='python_backend').json()['total'] == 0


def test_search_paginates_stably_and_clear_updates_membership(users):
    client, factory, a, _ = users
    for index in range(1, 4):
        task(client, factory, a, index, note='页内匹配')
    pages = [board(client, a, q='页内', limit=1, offset=offset).json() for offset in range(3)]
    ids = [page['items'][0]['id'] for page in pages]
    assert len(set(ids)) == 3 and all(page['total'] == 3 for page in pages)
    assert [page['has_more'] for page in pages] == [True, True, False]
    client.put('/api/account/revision-tasks/' + ids[0] + '/note', headers=auth(a), json={'content': '', 'expected_version': 1})
    assert board(client, a, q='页内', note_filter='with').json()['total'] == 2
    assert board(client, a, note_filter='without').json()['items'][0]['id'] == ids[0]


@pytest.mark.parametrize('params', [{'q': '长' * 101}, {'note_filter': 'yes'}])
def test_search_rejects_invalid_inputs_and_requires_login(users, params):
    client, _, a, _ = users
    assert board(client, a, **params).status_code == 422
    assert client.get('/api/account/revision-tasks?q=MySQL').status_code == 401
