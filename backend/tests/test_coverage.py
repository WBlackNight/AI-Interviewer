from sqlalchemy import event

from app.agent.skill_tree import SkillTree, SkillNode
from app.domain import Question
from app.rag.question_bank import QuestionBank
from app.services.coverage import catalog_coverage
from tests.test_ws_recovery import api


def assets():
    tree = {'java_backend': SkillTree('java_backend', 'Java', [SkillNode('MySQL'), SkillNode('empty'), SkillNode('coding')])}
    rows = [Question.from_dict({'id': str(i), 'position': 'java_backend', 'theme': theme, 'difficulty': level,
        'content': 'public question', 'source': source, 'is_coding': coding,
        'answer_points': [{'point': 'private-anchor', 'keywords': ['private-answer']}],
        'testcases': [{'input': 'private-input', 'expected': 'private-expected'}]})
        for i, (theme, level, source, coding) in enumerate([('MySQL', 'mid', 'builtin', False),
            ('MySQL', 'hard', 'unknown', False), ('coding', 'easy', 'builtin', True), ('orphan', 'easy', 'unknown', False)])]
    registry = {'builtin': {'label': 'Self authored', 'origin': 'self_authored', 'review_state': 'unreviewed', 'references': []}}
    return tree, QuestionBank(rows), registry


def test_matrix_separates_coding_empty_roots_orphans_and_source_states():
    trees, bank, registry = assets()
    result = catalog_coverage(trees, bank, registry, 'available')
    assert result['counts'] == {'all': 4, 'knowledge': 3, 'coding': 1, 'knowledge_themes': 2,
        'missing_cells': 4, 'under_two_questions': 1, 'unregistered': 2, 'not_reference_checked': 4, 'unmapped': 1}
    assert result['themes'][0]['missing_difficulties'] == ['easy']
    assert result['themes'][1]['missing_difficulties'] == ['easy', 'mid', 'hard']
    assert result['themes'][2]['coding_only'] and not result['themes'][2]['missing_difficulties']
    assert 'private-' not in str(result)
    empty = catalog_coverage({}, QuestionBank([]), {}, 'missing')
    assert not empty['themes'] and empty['counts']['all'] == 0 and empty['registry_state'] == 'missing'


def test_public_coverage_scopes_roles_validates_input_and_uses_no_database_or_search(api, monkeypatch):
    from app.api import routes
    client, factory = api
    trees, bank, registry = assets()
    monkeypatch.setattr(routes, 'load_assets', lambda settings: (trees, bank))
    monkeypatch.setattr(routes, 'load_registry', lambda path: (registry, 'available'))
    def forbidden(*args, **kwargs): raise AssertionError('coverage must not call search/model')
    monkeypatch.setattr(bank, 'search', forbidden); monkeypatch.setattr(routes, 'build_llm', forbidden)
    statements = []
    def record(*args): statements.append(args[2])
    engine = factory.kw['bind']; event.listen(engine, 'before_cursor_execute', record)
    try:
        response = client.get('/api/catalog/coverage?position=java_backend')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert 'private-' not in response.text and response.json()['counts']['all'] == 4
        assert client.get('/api/catalog/coverage?position=missing').status_code == 404
        assert client.get('/api/catalog/coverage?position=').status_code == 422
        assert client.get('/api/catalog/coverage?position=' + 'x'*65).status_code == 422
    finally: event.remove(engine, 'before_cursor_execute', record)
    assert statements == []


def test_role_selection_keeps_global_corpus_version_and_missing_registry_marks_unknown():
    trees, bank, registry = assets()
    trees['python_backend'] = SkillTree('python_backend', 'Python', [SkillNode('Python基础')])
    all_roles = catalog_coverage(trees, bank, registry, 'available')
    python = catalog_coverage(trees, bank, {}, 'invalid', 'python_backend')
    assert python['corpus_sha256'] == all_roles['corpus_sha256']
    assert python['counts']['all'] == 0 and python['counts']['missing_cells'] == 3
    invalid = catalog_coverage(trees, bank, {}, 'invalid', 'java_backend')
    assert invalid['counts']['unregistered'] == 4 and invalid['counts']['not_reference_checked'] == 4
