import pytest
from dataclasses import replace
from sqlalchemy import select, func

from app.domain import Question
from app.agent.skill_tree import SkillTree, SkillNode
from app.models.entities import QuestionMark, Question as StoredQuestion
from app.rag.question_bank import QuestionBank
from app.services.accounts import now_utc
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api

PATH = '/api/account/question-marks'


@pytest.fixture
def marked_api(users, monkeypatch):
    from app.api import question_marks
    client, factory, a, b = users
    trees = {'java_backend': SkillTree('java_backend', 'Java 后端', [SkillNode('MySQL')]),
             'python_backend': SkillTree('python_backend', 'Python 后端', [SkillNode('Python基础')])}
    questions = [Question.from_dict({'id': 'q' + str(i), 'position': 'java_backend' if i < 10 else 'python_backend',
        'theme': 'MySQL' if i < 9 else '编码' if i == 9 else 'Python基础', 'difficulty': 'mid',
        'content': '题干' + str(i), 'source': 'synthetic', 'is_coding': i == 9,
        'answer_points': [{'point': 'private-anchor', 'keywords': ['private-answer']}],
        'testcases': [{'input': 'private-input', 'expected': 'private-expected'}]}) for i in range(11)]
    bank = QuestionBank(questions)
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, bank))
    return client, factory, a, b, bank


def add(client, user, question_id='q0', position='java_backend'):
    result = client.post(PATH, headers=auth(user), json={'position': position, 'question_id': question_id})
    assert result.status_code == 200, result.text
    return result.json()


def listing(client, user, **params):
    result = client.get(PATH, headers=auth(user), params=params)
    assert result.status_code == 200, result.text
    return result.json()


def test_account_auth_isolation_and_private_response(marked_api):
    client, _, a, b, _ = marked_api
    mark = add(client, a)
    assert client.get(PATH).status_code == 401
    assert client.post(PATH, json={'position': 'java_backend', 'question_id': 'q0'}).status_code == 401
    assert listing(client, b)['total'] == 0
    assert client.get(PATH, headers=auth(a)).headers['cache-control'] == 'no-store'
    assert client.patch(PATH + '/' + mark['id'], headers=auth(b), json={'status': 'done', 'expected_version': 0}).status_code == 404
    assert client.delete(PATH + '/' + mark['id'] + '?expected_version=0', headers=auth(b)).status_code == 404
    assert listing(client, a)['total'] == 1


def test_duplicate_add_keeps_identity_status_version_and_timestamps(marked_api):
    client, _, a, _, _ = marked_api
    first = add(client, a)
    assert not first['reused']
    assert client.patch(PATH + '/' + first['id'], headers=auth(a), json={'status': 'done', 'expected_version': 0}).status_code == 200
    before = listing(client, a)['items'][0]
    assert add(client, a) == {'id': first['id'], 'reused': True}
    assert listing(client, a)['items'][0] == before
    assert before['status'] == 'done' and before['version'] == 1 and before['reviewed_at'].endswith('Z')


def test_status_version_prevents_stale_changes_and_removal(marked_api):
    client, _, a, _, _ = marked_api
    mark = add(client, a); url = PATH + '/' + mark['id']
    assert client.patch(url, headers=auth(a), json={'status': 'done', 'expected_version': 0}).json()['version'] == 1
    assert client.patch(url, headers=auth(a), json={'status': 'todo', 'expected_version': 0}).status_code == 409
    assert client.delete(url + '?expected_version=0', headers=auth(a)).status_code == 409
    before = listing(client, a)['items'][0]
    assert client.patch(url, headers=auth(a), json={'status': 'done', 'expected_version': 1}).json()['version'] == 1
    assert listing(client, a)['items'][0] == before
    assert client.patch(url, headers=auth(a), json={'status': 'todo', 'expected_version': 1}).json()['version'] == 2
    assert listing(client, a)['items'][0]['reviewed_at'] is None
    assert client.delete(url + '?expected_version=2', headers=auth(a)).json() == {'deleted': True}
    assert listing(client, a)['total'] == 0


def test_current_asset_resolution_whitelist_unavailable_and_no_model_calls(marked_api, monkeypatch):
    client, factory, a, _, bank = marked_api
    first = add(client, a); add(client, a, 'q9')
    def forbidden(*args, **kwargs): raise AssertionError('题单不能调用召回或模型')
    monkeypatch.setattr(bank, 'search', forbidden)
    rows = listing(client, a)['items']
    assert all(set(row['question']) == {'theme', 'difficulty', 'content', 'source', 'is_coding'} for row in rows)
    assert 'private-' not in str(rows)
    assert not next(row for row in rows if row['question_id'] == 'q9')['can_practice']
    from app.api import question_marks
    trees, _ = question_marks.load_assets(None)
    updated = QuestionBank([replace(q, content='当前更新后的题干') if q.id == 'q0' else q for q in bank.questions])
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, updated))
    row = next(row for row in listing(client, a)['items'] if row['id'] == first['id'])
    assert row['question']['content'] == '当前更新后的题干'
    unavailable = QuestionBank([q for q in updated.questions if q.id != 'q0'])
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, unavailable))
    result = listing(client, a)
    row = next(row for row in result['items'] if row['id'] == first['id'])
    assert not row['available'] and not row['can_practice'] and row['question'] is None
    assert result['counts']['unavailable'] == 1
    assert add(client, a)['reused']  # 下架后已有收藏仍可重复确认，不伪造新题。
    with factory() as db:
        assert set(QuestionMark.__table__.columns.keys()) == {'id', 'account_id', 'position', 'question_id', 'status', 'version', 'created_at', 'reviewed_at'}


def test_filters_counts_and_stable_pagination(marked_api):
    client, _, a, _, _ = marked_api
    for i in range(11): add(client, a, 'q' + str(i), 'java_backend' if i < 10 else 'python_backend')
    first = listing(client, a, limit=8); second = listing(client, a, offset=8, limit=8)
    assert first['has_more'] and not second['has_more'] and len(first['items']) == 8 and len(second['items']) == 3
    assert len({row['id'] for row in first['items'] + second['items']}) == 11
    mark = first['items'][0]
    client.patch(PATH + '/' + mark['id'], headers=auth(a), json={'status': 'done', 'expected_version': 0})
    done = listing(client, a, status='done')
    assert done['total'] == 1 and done['counts'] == {'all': 11, 'todo': 10, 'done': 1, 'unavailable': 0}
    assert listing(client, a, position='java_backend')['counts']['all'] == 10
    assert listing(client, a, position='missing')['total'] == 0


def test_invalid_inputs_unknown_questions_and_capacity(marked_api):
    client, factory, a, _, _ = marked_api
    for params in [{'limit': 25}, {'offset': -1}, {'status': 'mastered'}, {'position': ''}]:
        assert client.get(PATH, headers=auth(a), params=params).status_code == 422
    for payload in [{'position': 'java_backend', 'question_id': 'q0', 'content': 'injected'}, {'position': 'x'*65, 'question_id': 'q0'}]:
        assert client.post(PATH, headers=auth(a), json=payload).status_code == 422
    assert client.post(PATH, headers=auth(a), json={'position': 'python_backend', 'question_id': 'q0'}).status_code == 404
    assert client.post(PATH, headers=auth(a), json={'position': 'java_backend', 'question_id': 'missing'}).status_code == 404
    mark = add(client, a)
    assert client.patch(PATH + '/' + mark['id'], headers=auth(a), json={'status': 'done', 'expected_version': True}).status_code == 422
    with factory() as db:
        db.add_all([QuestionMark(account_id=a['account']['id'], position='old', question_id=str(i), status='todo', version=0, created_at=now_utc()) for i in range(499)])
        db.commit()
    assert add(client, a)['reused']
    assert client.post(PATH, headers=auth(a), json={'position': 'java_backend', 'question_id': 'q1'}).status_code == 409


def test_account_deletion_cleans_only_own_marks_and_preserves_question_bank(marked_api):
    client, factory, a, b, _ = marked_api
    add(client, a); add(client, b)
    with factory() as db: before = db.scalar(select(func.count()).select_from(StoredQuestion))
    assert client.request('DELETE', '/api/account', headers=auth(a), json={'password': PASSWORD}).status_code == 200
    assert listing(client, b)['total'] == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(QuestionMark)) == 1
        assert db.scalar(select(func.count()).select_from(StoredQuestion)) == before
    assert client.get(PATH, headers=auth(a)).status_code == 401


def test_search_is_literal_casefolded_and_counts_precede_status(marked_api, monkeypatch):
    client, _, a, b, bank = marked_api
    from app.api import question_marks
    trees, _ = question_marks.load_assets(None)
    updated = QuestionBank([replace(q, content='100%_ MySQL 索引') if q.id == 'q0' else q for q in bank.questions])
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, updated))
    first = add(client, a); add(client, a, 'q1'); add(client, b, 'q0')
    client.patch(PATH + '/' + first['id'], headers=auth(a), json={'status': 'done', 'expected_version': 0})
    result = listing(client, a, q=' mysql ', status='todo')
    assert result['query'] == 'mysql' and result['total'] == 1  # 根主题MySQL也参与匹配。
    assert result['counts'] == {'all': 2, 'todo': 1, 'done': 1, 'unavailable': 0}
    assert listing(client, a, q='%')['total'] == 1
    assert listing(client, a, q='_')['total'] == 1
    assert listing(client, a, q='Q0')['items'][0]['id'] == first['id']
    assert listing(client, a, q='synthetic')['total'] == 2
    assert listing(client, b, q='q1')['total'] == 0
    assert listing(client, a, q='q0', position='python_backend')['total'] == 0


def test_search_resolves_current_content_and_keeps_unavailable_ids_searchable(marked_api, monkeypatch):
    client, _, a, _, bank = marked_api
    from app.api import question_marks
    trees, _ = question_marks.load_assets(None)
    mark = add(client, a)
    assert listing(client, a, q='题干0')['total'] == 1
    changed = QuestionBank([replace(q, content='新内容', source='new-source') if q.id == 'q0' else q for q in bank.questions])
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, changed))
    assert listing(client, a, q='题干0')['total'] == 0 and listing(client, a, q='new-source')['total'] == 1
    unavailable = QuestionBank([q for q in changed.questions if q.id != 'q0'])
    monkeypatch.setattr(question_marks, 'load_assets', lambda settings: (trees, unavailable))
    result = listing(client, a, q='Q0')
    assert result['counts']['unavailable'] == 1 and result['items'][0]['id'] == mark['id']
    assert result['items'][0]['question'] is None


def test_search_limit_and_whitespace_do_not_change_default_list(marked_api):
    client, _, a, _, _ = marked_api
    add(client, a)
    assert listing(client, a, q='  ') == listing(client, a)
    assert client.get(PATH, headers=auth(a), params={'q': '字'*101}).status_code == 422
    assert listing(client, a, q='字'*100)['total'] == 0
