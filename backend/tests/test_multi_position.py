import json

import pytest

from app.config import Settings
from app.factories import load_assets
from app.agent.planner import HeuristicPlanner
from app.rag.retriever import QuestionFilter
from app.rag.question_bank import QuestionBank
from app.domain import ResumeData
from tests.test_ws_recovery import api, connect


@pytest.mark.parametrize('position', ['java_backend', 'python_backend'])
@pytest.mark.parametrize('difficulty', ['easy', 'mid', 'hard'])
def test_each_position_plans_and_selects_only_its_own_questions(position, difficulty):
    trees, bank = load_assets(Settings(_env_file=None))
    tree = trees[position]
    plan = HeuristicPlanner(tree).build_plan(position=position, difficulty=difficulty,
        resume=ResumeData(), bank=bank, max_themes=3)
    assert plan and sum(p.weight for p in plan) == pytest.approx(1)
    for item in plan:
        assert item.theme in tree.root_names()
        q = bank.next_question(position=position, theme=item.theme, difficulty=difficulty, exclude=set())
        assert q.position == position and not q.is_coding
    assert bank.next_coding_question(position=position, exclude=set()).position == position
    own = {q.id for q in bank.questions if q.position == position}
    assert bank.next_coding_question(position=position, exclude=own) is None
    for item in plan:
        assert bank.next_question(position=position, theme=item.theme, difficulty=difficulty, exclude=own) is None


def test_catalog_counts_and_labels_are_data_driven_and_read_only(api, monkeypatch):
    from app.api import routes
    client, _ = api
    monkeypatch.setattr(routes, 'build_llm', lambda *a: pytest.fail('catalog must not call LLM'))
    positions = {p['id']: p for p in client.get('/api/positions').json()['positions']}
    assert positions['java_backend']['question_count'] == 20
    assert positions['python_backend']['question_count'] == 20
    assert positions['python_backend']['display_name'] == 'Python 后端'
    trees, bank = load_assets(Settings(_env_file=None))
    monkeypatch.setattr(routes, 'load_assets', lambda _: (trees, QuestionBank([q for q in bank if q.position == 'java_backend'])))
    assert [p['id'] for p in client.get('/api/positions').json()['positions']] == ['java_backend']


@pytest.mark.parametrize('position', ['java_backend','python_backend'])
def test_api_session_and_report_use_selected_position(api, position):
    client, _ = api
    created = client.post('/api/interview', json={'position':position}).json()
    with connect(client, created) as (_, snapshot):
        _,bank=load_assets(Settings(_env_file=None))
        assert bank.get(snapshot['current_question']['id']).position==position
    headers = {'X-Interview-Token':created['access_token']}
    summary = client.get('/api/interview/'+created['interview_id'], headers=headers).json()
    report = client.get('/api/interview/'+created['interview_id']+'/report', headers=headers).json()
    assert report['position'] == summary['position'] == position
    assert report['position_display_name'] == summary['position_display_name']


def test_python_demo_bank_contract_and_coding_fixtures():
    trees, bank = load_assets(Settings(_env_file=None))
    python = [q for q in bank if q.position == 'python_backend']
    assert len(python) == 20
    assert len({q.id for q in bank}) == len(bank)
    assert all(q.theme in trees['python_backend'].root_names() and q.answer_points for q in python)
    assert all(q.source == 'builtin-python-demo-v1' or q.source.startswith('original-') for q in python)
    code = next(q for q in python if q.is_coding)
    assert len(code.testcases) == 6
    for case in code.testcases:
        lines = case.input.split('\n')
        numbers, target = list(map(int, lines[0].split())), int(lines[1])
        seen, found = {}, []
        for index, value in enumerate(numbers):
            if target-value in seen:
                found = [seen[target-value], index]; break
            seen[value] = index
        assert found == json.loads(case.expected)


def test_unknown_position_is_not_silently_changed(api):
    client, _ = api
    assert client.post('/api/interview', json={'position':'unknown'}).status_code == 404
