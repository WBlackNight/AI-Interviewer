import pytest
from sqlalchemy import event

from app.agent.skill_tree import SkillTree, SkillNode
from app.domain import Question
from app.rag.question_bank import QuestionBank
from tests.test_ws_recovery import api


@pytest.fixture
def catalog_api(api, monkeypatch):
    from app.api import routes
    client, factory = api
    trees = {'java_backend': SkillTree('java_backend', 'Java 后端', [SkillNode('MySQL'), SkillNode('Redis')]),
             'python_backend': SkillTree('python_backend', 'Python 后端', [SkillNode('Python基础')])}
    rows = [('a', 'java_backend', 'MySQL', 'easy', '100% MYSQL 范围查询', False),
            ('b', 'java_backend', 'MySQL', 'hard', '索引结构', False),
            ('c', 'java_backend', '编码', 'mid', 'Python code', True),
            ('d', 'java_backend', '旧主题', 'mid', '不可用于当前专项', False),
            ('e', 'python_backend', 'Python基础', 'mid', '迭代器', False)]
    bank = QuestionBank([Question.from_dict({'id': key, 'position': pos, 'theme': theme, 'difficulty': level,
        'content': content, 'is_coding': coding, 'source': 'synthetic-catalog',
        'answer_points': [{'point': 'private-anchor', 'keywords': ['private-keyword']}],
        'testcases': [{'input': 'private-input', 'expected': 'private-expected'}]})
        for key, pos, theme, level, content, coding in rows])
    monkeypatch.setattr(routes, 'load_assets', lambda settings: (trees, bank))
    return client, factory, bank


def test_catalog_public_fields_and_role_metadata(catalog_api):
    client, _, _ = catalog_api
    response = client.get('/api/catalog')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    result = response.json()
    assert result['position'] == 'java_backend' and result['total'] == 4
    assert result['counts'] == {'all': 4, 'knowledge': 3, 'coding': 1}
    assert {item['id'] for item in result['positions']} == {'java_backend', 'python_backend'}
    assert all(set(item) == {'id', 'position', 'theme', 'difficulty', 'content', 'source', 'is_coding', 'can_practice'} for item in result['items'])
    assert 'private-' not in response.text


def test_exact_difficulty_theme_and_literal_search(catalog_api):
    client, _, _ = catalog_api
    result = client.get('/api/catalog?theme=MySQL&difficulty=mid').json()
    assert result['total'] == 0 and result['items'] == []  # 浏览不使用出题的难度放宽。
    result = client.get('/api/catalog', params={'q': ' mysql ', 'theme': 'MySQL', 'difficulty': 'easy'}).json()
    assert result['query'] == 'mysql' and [item['id'] for item in result['items']] == ['a']
    assert client.get('/api/catalog', params={'q': '%'}).json()['total'] == 1
    assert client.get('/api/catalog', params={'q': '_'}).json()['total'] == 0
    assert client.get('/api/catalog?position=python_backend').json()['total'] == 1


def test_kind_counts_precede_kind_filter_and_pagination_is_stable(catalog_api):
    client, _, _ = catalog_api
    coding = client.get('/api/catalog?kind=coding').json()
    assert coding['total'] == 1 and coding['items'][0]['id'] == 'c'
    assert coding['counts'] == {'all': 4, 'knowledge': 3, 'coding': 1}
    pages = [client.get('/api/catalog', params={'limit': 1, 'offset': offset}).json() for offset in range(4)]
    assert len({page['items'][0]['id'] for page in pages}) == 4
    assert [page['has_more'] for page in pages] == [True, True, True, False]
    assert client.get('/api/catalog?limit=1&offset=4').json()['items'] == []


def test_only_available_knowledge_roots_can_start_topic_practice(catalog_api):
    client, _, _ = catalog_api
    result = client.get('/api/catalog').json()
    assert {item['id'] for item in result['items'] if item['can_practice']} == {'a', 'b'}
    themes = {item['name']: item for item in result['positions'][0]['themes']}
    assert themes['MySQL']['can_practice'] and themes['MySQL']['question_count'] == 2
    assert not themes['Redis']['can_practice'] and themes['Redis']['question_count'] == 0
    assert not themes['旧主题']['can_practice'] and not themes['编码']['can_practice']
    assert result['positions'][0]['practice_theme_limit'] == 3


def test_input_bounds_and_unknown_role(catalog_api):
    client, _, _ = catalog_api
    for params in [{'difficulty': 'normal'}, {'kind': 'unknown'}, {'q': '字' * 101}, {'offset': -1},
                   {'limit': 25}, {'position': ''}, {'theme': '字' * 65}, {'offset': 1000001}]:
        assert client.get('/api/catalog', params=params).status_code == 422, params
    assert client.get('/api/catalog?position=missing').status_code == 404
    empty = client.get('/api/catalog?theme=missing').json()
    assert empty['total'] == 0 and len(empty['positions']) == 2


def test_browsing_does_not_search_models_or_touch_business_database(catalog_api, monkeypatch):
    client, factory, bank = catalog_api
    def forbidden(*args, **kwargs):
        raise AssertionError('目录读取不能调用检索或模型')
    monkeypatch.setattr(bank, 'search', forbidden)
    from app.api import routes
    monkeypatch.setattr(routes, 'build_llm', forbidden)
    statements = []
    def record(*args): statements.append(args[2])
    engine = factory.kw['bind']
    event.listen(engine, 'before_cursor_execute', record)
    try:
        assert client.get('/api/catalog').status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert statements == []


def test_empty_assets_return_an_empty_catalog(catalog_api, monkeypatch):
    client, _, _ = catalog_api
    from app.api import routes
    monkeypatch.setattr(routes, 'load_assets', lambda settings: ({}, QuestionBank([])))
    result = client.get('/api/catalog').json()
    assert result['positions'] == result['items'] == []
    assert result['position'] is None and result['total'] == 0
