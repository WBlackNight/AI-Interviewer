import pytest
from sqlalchemy import func, select

from app.agent.prober import SkillTreeProber
from app.agent.scorer import HeuristicScorer
from app.agent.session import InterviewSession
from app.agent.skill_tree import SkillNode, SkillTree
from app.domain import PlanItem, Question
from app.models.entities import Interview
from app.rag.question_bank import QuestionBank
from app.services.assessment import assessment_summary
from app.services.practice import timed_plan
from tests.test_ws_recovery import api


def bank():
    return QuestionBank([Question(id=f'q-{index}', position='role', theme='主题',
                                 difficulty='mid', content='请说明这个场景的处理思路')
                         for index in range(6)])


def test_selection_varies_between_interviews_and_survives_restore():
    questions = bank()
    tree = SkillTree('role', '方向', [SkillNode('主题')])
    def session(identity):
        return InterviewSession(interview_id=identity, position='role',
            plan=[PlanItem('主题', 1, 'mid', 3, False)], bank=questions,
            scorer=HeuristicScorer(), prober=SkillTreeProber(tree))
    selected = set()
    for index in range(20):
        current = session(str(index))
        current.start()
        first = current.current_question['id']
        selected.add(first)
        restored = session(str(index))
        restored.restore(current.snapshot())
        current.handle_answer('跳过')
        restored.handle_answer('跳过')
        assert current.current_question['id'] == restored.current_question['id']
        assert current.current_question['id'] != first
    assert len(selected) > 1
    legacy = session('legacy')
    legacy.start()
    snapshot = legacy.snapshot()
    snapshot.pop('selection_seed')
    restored = session('legacy')
    restored.restore(snapshot)
    restored.handle_answer('跳过')
    expected = questions.next_question(position='role', theme='主题', difficulty='mid',
                                       exclude=set(snapshot['asked']))
    assert restored.current_question['id'] == expected.id


def test_allocation_caps_auto_and_timed_plans_to_current_capacity():
    questions = bank()
    plan = [PlanItem('主题', .8, 'mid', 10, False), PlanItem('空主题', .2, 'mid', 2, False)]
    automatic = timed_plan(plan, questions, 'role', None)
    assert len(automatic) == 1 and automatic[0].question_count == 6
    assert automatic[0].weight == 1
    assert sum(item.question_count for item in timed_plan(plan, questions, 'role', 15)) == 4
    assert timed_plan([], questions, 'role', 5) == []
    with pytest.raises(ValueError):
        timed_plan(plan, questions, 'role', 20)


def test_preview_does_not_create_resources_and_matches_topic_practice(api, monkeypatch):
    from app.api import practice_config, routes
    client, factory = api
    monkeypatch.setattr(practice_config, 'get_settings', lambda: routes.settings)
    configuration = client.get('/api/practice/config').json()
    assert configuration['question_count'] == 120
    assert len(configuration['positions']) == 6
    assert 'answer_points' not in str(configuration)
    payload = {'position': 'java_backend', 'themes': ['MySQL', 'Redis'], 'duration_minutes': 15}
    preview = client.post('/api/practice/preview', json=payload)
    assert preview.status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 0
    created = client.post('/api/interview', json=payload).json()
    assert preview.json()['themes'] == [{'name': row['theme'], 'question_count': row['question_count']}
                                        for row in created['plan']]
    assert preview.json()['main_question_count'] == 4
    assert client.post('/api/practice/preview', json={**payload, 'duration_minutes': 30}).status_code == 422
    assert client.post('/api/practice/preview', json={**payload, 'themes': ['不存在']}).status_code == 422


def test_assessment_uses_observed_points_without_inventing_strengths():
    rows = [dict(main_question_id='q', theme='主题', content='问题', score=4, probe_depth=0,
                 key_points_hit=['已说明背景'], key_points_missed=['解释原因'], evidence='原有依据'),
            dict(main_question_id='q', theme='主题', content='追问', score=8, probe_depth=1,
                 key_points_hit=['解释原因'], key_points_missed=[], evidence='追问依据')]
    result = assessment_summary(rows, threshold=7, complete=True)
    assert result['questions'][0]['score'] == 6
    assert result['questions'][0]['gaps'] == []
    assert result['strengths'] == []
    assert len(result['priorities']) == 1
    assert assessment_summary([], threshold=7, complete=False)['status'] == 'partial'
