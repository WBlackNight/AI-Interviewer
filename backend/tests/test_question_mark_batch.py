"""批量题单：原子性、账户隔离、容量与原有版本语义。"""
import pytest

from app.models.entities import QuestionMark
from app.services.accounts import now_utc
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_question_marks import marked_api, add, listing, PATH


def collect(client, user, *ids):
    return client.post(PATH + '/batch', headers=auth(user), json={
        'items': [{'position': 'java_backend', 'question_id': qid} for qid in ids]})


def change(client, user, rows, action):
    return client.patch(PATH + '/batch', headers=auth(user), json={
        'action': action, 'items': [{'id': row['id'], 'expected_version': row['version']} for row in rows]})


def test_batch_collect_preserves_existing_state_and_is_repeatable(marked_api):
    client, _, a, b, _ = marked_api
    old = add(client, a)
    client.patch(PATH + '/' + old['id'], headers=auth(a), json={'status': 'done', 'expected_version': 0})
    before = listing(client, a)['items'][0]
    result = collect(client, a, 'q0', 'q1', 'q2')
    assert result.status_code == 200, result.text
    assert result.json()['added'] == 2 and result.json()['reused'] == 1
    assert result.json()['items'][0] == {'id': old['id'], 'reused': True}
    assert next(row for row in listing(client, a)['items'] if row['id'] == old['id']) == before
    assert collect(client, a, 'q0', 'q1', 'q2').json()['added'] == 0
    assert listing(client, a)['total'] == 3 and listing(client, b)['total'] == 0
    assert 'private-' not in result.text


def test_collect_invalid_question_rolls_back_entire_batch(marked_api):
    client, _, a, _, _ = marked_api
    assert collect(client, a, 'q0', 'not-in-bank').status_code == 404
    assert listing(client, a)['total'] == 0


def test_capacity_counts_only_new_rows_and_never_partially_adds(marked_api):
    client, factory, a, _, _ = marked_api
    add(client, a)
    with factory() as db:
        db.add_all([QuestionMark(account_id=a['account']['id'], position='old', question_id=str(i),
            status='todo', version=0, created_at=now_utc()) for i in range(498)])
        db.commit()
    assert collect(client, a, 'q0', 'q1', 'q2').status_code == 409
    assert listing(client, a)['total'] == 499
    result = collect(client, a, 'q0', 'q1')
    assert result.status_code == 200 and result.json()['added'] == 1
    assert collect(client, a, 'q0', 'q1').json()['reused'] == 2
    # 兼容外部恢复的超额旧数据：仍可确认已有收藏，但不能继续新增。
    with factory() as db:
        db.add(QuestionMark(account_id=a['account']['id'], position='old', question_id='restored',
            status='todo', version=0, created_at=now_utc()))
        db.commit()
    assert collect(client, a, 'q0', 'q1').json()['reused'] == 2
    assert collect(client, a, 'q2').status_code == 409


def test_status_updates_keep_noop_versions_and_review_dates(marked_api):
    client, _, a, _, _ = marked_api
    collect(client, a, 'q0', 'q1', 'q2')
    rows = listing(client, a)['items']
    response = change(client, a, rows, 'done')
    assert response.status_code == 200, response.text
    assert response.json() == {'action': 'done', 'selected': 3, 'changed': 3}
    done = listing(client, a)['items']
    assert all(row['version'] == 1 and row['reviewed_at'] for row in done)
    assert change(client, a, done, 'done').json()['changed'] == 0
    assert listing(client, a)['items'] == done
    assert change(client, a, done[:2], 'todo').json()['changed'] == 2
    restored = listing(client, a)['items']
    assert all(row['version'] == 2 and row['reviewed_at'] is None for row in restored[:2])
    assert restored[2] == done[2]


@pytest.mark.parametrize('action', ['todo', 'done', 'remove'])
def test_stale_version_does_not_modify_any_selected_row(marked_api, action):
    client, _, a, _, _ = marked_api
    collect(client, a, 'q0', 'q1')
    stale = listing(client, a)['items']
    client.patch(PATH + '/' + stale[1]['id'], headers=auth(a), json={'status': 'done', 'expected_version': 0})
    before = listing(client, a)
    assert change(client, a, stale, action).status_code == 409
    assert listing(client, a) == before


def test_foreign_or_removed_rows_prevent_partial_changes(marked_api):
    client, _, a, b, _ = marked_api
    add(client, a, 'q0'); add(client, b, 'q1')
    own = listing(client, a)['items']; other = listing(client, b)['items']
    assert change(client, a, own + other, 'remove').status_code == 404
    assert listing(client, a)['items'] == own and listing(client, b)['items'] == other
    assert change(client, a, own, 'remove').json()['changed'] == 1
    assert listing(client, a)['total'] == 0
    assert change(client, a, own, 'remove').status_code == 404
    assert listing(client, b)['items'] == other


def test_batch_authentication_and_strict_payloads(marked_api):
    client, _, a, _, _ = marked_api
    assert client.post(PATH + '/batch', json={'items': []}).status_code == 401
    assert client.patch(PATH + '/batch', json={'items': [], 'action': 'done'}).status_code == 401
    item = {'position': 'java_backend', 'question_id': 'q0'}
    for payload in [{'items': []}, {'items': [item] * 25}, {'items': [item, item]},
                    {'items': [dict(item, answer='injected')]}, {'items': [item], 'extra': True}]:
        assert client.post(PATH + '/batch', headers=auth(a), json=payload).status_code == 422
    mark = add(client, a)
    reference = {'id': mark['id'], 'expected_version': 0}
    for items, action in [([], 'done'), ([reference] * 25, 'done'), ([reference] * 2, 'done'),
                          ([dict(reference, expected_version=True)], 'done'), ([reference], 'mastered')]:
        assert client.patch(PATH + '/batch', headers=auth(a), json={'items': items, 'action': action}).status_code == 422
    assert listing(client, a)['items'][0]['version'] == 0
