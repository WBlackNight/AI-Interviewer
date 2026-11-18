import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models.entities import AssistantConversation
from app.services.accounts import AuthThrottle, now_utc
from app.services.assistant import validate_calls
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api


@pytest.fixture(autouse=True)
def offline_assistant(monkeypatch):
    from app.api import assistant
    monkeypatch.setattr(assistant, 'get_settings', lambda: Settings(_env_file=None, llm_api_key=None))
    monkeypatch.setattr(assistant, 'throttle', AuthThrottle())


def create(client, user, position='java_backend'):
    result = client.post('/api/assistant/conversations', headers=auth(user), json={'position': position})
    assert result.status_code == 200, result.text
    return result.json()


def send(client, user, row, **updates):
    body = {'text': '请解释 MySQL 索引的使用边界', 'request_id': uuid.uuid4().hex,
            'expected_version': row['version'], **updates}
    return client.post('/api/assistant/conversations/' + row['id'] + '/turns', headers=auth(user), json=body)


def frames(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def test_demo_requires_account_is_local_and_does_not_persist(users):
    client, factory, actor, _ = users
    assert client.get('/assistant').status_code == 200
    assert client.get('/assistant.html', follow_redirects=False).headers['location'] == '/assistant'
    assert client.get('/assets/assistant.js').status_code == 200
    data = {'position': 'english_interview', 'text': 'Tell me about yourself'}
    assert client.post('/api/assistant/demo', json=data).status_code == 401
    response = client.post('/api/assistant/demo', json=data, headers=auth(actor))
    events = frames(response)
    assert response.headers['cache-control'] == 'no-store'
    assert next(item for item in events if item['type'] == 'mode')['value'] == 'local'
    assert events[-1]['type'] == 'done'
    assert 'answer_points' not in response.text and 'testcases' not in response.text
    with factory() as db:
        assert not list(db.scalars(select(AssistantConversation)))
    assert client.get('/api/assistant/conversations').status_code == 401


def test_histories_are_private_versioned_and_replay_without_duplicate_turn(users):
    client, factory, a, b = users
    row = create(client, a)
    key = uuid.uuid4().hex
    events = frames(send(client, a, row, request_id=key, text='联系我 private@example.org，解释索引'))
    assert events[-1] == {'type': 'done', 'version': 1}
    saved = client.get('/api/assistant/conversations/' + row['id'], headers=auth(a)).json()
    assert len(saved['messages']) == 2 and '[EMAIL]' in saved['messages'][0]['content']
    replay = frames(send(client, a, row, request_id=key, text='联系我 private@example.org，解释索引'))
    assert replay[-1]['replayed'] and replay[-1]['version'] == 1
    assert send(client, a, row).status_code == 409
    assert client.get('/api/assistant/conversations', headers=auth(b)).json()['items'] == []
    for method, path, body in [('GET', '', None), ('POST', '/turns', {'text': '索引', 'request_id': uuid.uuid4().hex, 'expected_version': 1}),
                               ('PATCH', '', {'title': '改名', 'expected_version': 1}), ('DELETE', '?expected_version=1', None)]:
        assert client.request(method, '/api/assistant/conversations/' + row['id'] + path, headers=auth(b), json=body).status_code == 404
    with factory() as db:
        assert db.get(AssistantConversation, row['id']).busy_id is None


def test_rename_delete_and_account_delete_remove_assistant_data(users):
    client, factory, a, _ = users
    row = create(client, a)
    path = '/api/assistant/conversations/' + row['id']
    changed = client.patch(path, headers=auth(a), json={'title': '我的准备', 'expected_version': 0})
    assert changed.status_code == 200 and changed.json()['version'] == 1
    assert client.delete(path + '?expected_version=0', headers=auth(a)).status_code == 409
    assert client.delete(path + '?expected_version=1', headers=auth(a)).json()['deleted']
    create(client, a)
    assert client.request('DELETE', '/api/account', headers=auth(a), json={'password': PASSWORD}).status_code == 200
    with factory() as db:
        assert not list(db.scalars(select(AssistantConversation)))


def test_busy_turn_and_expired_lease_are_handled(users):
    client, factory, a, _ = users
    row = create(client, a)
    with factory() as db:
        current = db.get(AssistantConversation, row['id'])
        current.busy_id, current.busy_until = 'a' * 32, now_utc() + timedelta(minutes=1)
        db.commit()
    assert send(client, a, row).status_code == 409
    with factory() as db:
        db.get(AssistantConversation, row['id']).busy_until = now_utc() - timedelta(seconds=1)
        db.commit()
    assert frames(send(client, a, row))[-1]['type'] == 'done'


@pytest.mark.parametrize('name,args,include', [
    ('delete_account', {}, True), ('practice_focus', {}, False),
    ('practice_focus', {'account_id': 'other'}, True), ('search_questions', {'query': ''}, False),
    ('search_questions', {'query': 'x', 'position': 'other'}, True)])
def test_tool_allowlist_rejects_arbitrary_execution(name, args, include):
    with pytest.raises(ValueError):
        validate_calls({'tool_calls': [{'id': 't1', 'function': {'name': name, 'arguments': json.dumps(args)}}]}, include)


class FakeModel:
    def __init__(self, failure=False):
        self.failure, self.closed, self.messages = failure, False, []
    def tool_call(self, messages, tools):
        assert not any(tool['function']['name'] == 'practice_focus' for tool in tools)
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'search1', 'type': 'function',
            'function': {'name': 'search_questions', 'arguments': '{"query":"MySQL 索引"}'}}]}
    def stream_chat(self, messages):
        self.messages = messages
        yield '先说明查询场景，'
        if self.failure:
            raise RuntimeError('private-provider-error')
        yield '再解释执行计划与写入成本。'
    def close(self):
        self.closed = True


def test_function_calling_is_grounded_and_replayed_without_model_charge(users, monkeypatch):
    from app.services import assistant
    client, _, a, _ = users
    models = []
    def build(_):
        model = FakeModel(); models.append(model); return model
    monkeypatch.setattr(assistant, 'build_llm', build)
    row = create(client, a)
    key = uuid.uuid4().hex
    events = frames(send(client, a, row, request_id=key))
    evidence = next(item for item in events if item['type'] == 'evidence')
    assert evidence['workflow'] == 'function_calling'
    assert any(item['role'] == 'tool' for item in models[0].messages)
    assert [item['text'] for item in events if item['type'] == 'delta'] == ['先说明查询场景，', '再解释执行计划与写入成本。']
    frames(send(client, a, row, request_id=key))
    assert len(models) == 1 and models[0].closed


def test_broken_stream_does_not_save_partial_and_leaves_retry_possible(users, monkeypatch):
    from app.services import assistant
    client, factory, a, _ = users
    model = FakeModel(failure=True)
    monkeypatch.setattr(assistant, 'build_llm', lambda _: model)
    row = create(client, a)
    response = send(client, a, row)
    events = frames(response)
    assert events[-1]['type'] == 'error' and 'private-provider-error' not in response.text
    with factory() as db:
        current = db.get(AssistantConversation, row['id'])
        assert not current.messages and current.version == 0 and current.busy_id is None
    assert model.closed


def test_focus_is_only_read_with_explicit_consent(users, monkeypatch):
    from app.api import assistant
    reads = []
    monkeypatch.setattr(assistant, 'latest_practice_focus', lambda db, account_id, *args: reads.append(account_id) or None)
    client, _, a, _ = users
    row = create(client, a)
    frames(send(client, a, row))
    assert not reads
    row['version'] = 1
    frames(send(client, a, row, include_focus=True))
    assert reads == [a['account']['id']]


def test_payloads_are_bounded_and_validation_does_not_echo_text(users):
    client, _, a, _ = users
    row = create(client, a)
    for changes in ({'text': 'private-text-' * 200}, {'expected_version': True}, {'include_focus': 'true'}, {'text': '   '}):
        response = send(client, a, row, **changes)
        assert response.status_code == 422 and 'private-text-' not in response.text
    assert client.post('/api/assistant/conversations', headers=auth(a), json={'position': 'missing'}).status_code == 422


def test_budget_failure_does_not_make_another_unmetered_call(users, monkeypatch):
    from app.services import assistant
    from app.llm.errors import BudgetExceeded
    class Unmetered(FakeModel):
        def tool_call(self, *args):
            raise BudgetExceeded('Synthetic missing usage')
        def stream_chat(self, *args):
            pytest.fail('must not make another call after budget failure')
    model = Unmetered()
    monkeypatch.setattr(assistant, 'build_llm', lambda _: model)
    client, _, a, _ = users
    events = frames(send(client, a, create(client, a)))
    assert next(item for item in events if item['type'] == 'mode')['value'] == 'local'
    assert events[-1]['type'] == 'done' and model.closed


def test_index_knowledge_is_grounded_and_action_respects_duration(users):
    from app.factories import load_assets
    from app.services.assistant import retrieve
    trees, bank = load_assets(Settings(_env_file=None, llm_api_key=None))
    sources = retrieve(bank, 'java_backend', '联合索引')
    guide = next(item for item in sources if item['id'] == 'G1')
    assert 'WHERE' in guide['content'] and '不是SQL' in guide['content']
    assert 'testcases' not in json.dumps(sources) and 'answer_points' not in json.dumps(sources)
    client, _, actor, _ = users
    events = frames(client.post('/api/assistant/demo', json={'position': 'java_backend', 'text': '我有15分钟准备索引题'}, headers=auth(actor)))
    evidence = next(item for item in events if item['type'] == 'evidence')
    assert 'duration=15' in evidence['actions'][0]['href']
