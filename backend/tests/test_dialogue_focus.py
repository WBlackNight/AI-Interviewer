"""用户可跳过，追问不跑题；不使用外部模型或设备。"""
from pathlib import Path

import pytest

from app.agent.prober import SkillTreeProber
from app.agent.skill_tree import load_skill_tree
from app.config import Settings
from app.domain import PlanItem, ScoreResult
from app.factories import load_assets
from tests.test_session_flow import _bank, _session

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('answer', ['跳过', '跳过这题。', '下一题', '这题不会', '我不知道', 'skip!'])
def test_explicit_skip_saves_unanswered_record_without_calling_scorer(answer):
    class ForbiddenScorer:
        def score(self, *args):
            pytest.fail('Explicit skip must not call scoring or a paid model')
    session = _session(_bank(), scorer=ForbiddenScorer(), plan=[
        PlanItem('MySQL', .5, 'mid', 1), PlanItem('Redis', .5, 'mid', 1)])
    session.start()
    events = session.handle_answer(answer)
    questions = [e for e in events if e['type'] == 'question']
    assert questions and questions[0]['theme'] == 'Redis' and not questions[0].get('is_probe')
    assert session.records[0].answer_text == answer
    assert session.records[0].result.score == 0
    assert session.records[0].result.origin.scorer_version == 'explicit-skip-v1'
    assert any(e['type'] == 'answer_ack' for e in events)


def test_uncertain_technical_explanation_is_not_a_skip():
    session = _session(_bank(), plan=[PlanItem('MySQL', 1, 'mid', 1)])
    session.start()
    events = session.handle_answer('我不知道是否需要加锁，想先分析访问模式。')
    assert any(e['type'] == 'question' and e.get('is_probe') for e in events)
    assert session.records[0].result.origin.scorer_version != 'explicit-skip-v1'


def test_generator_probe_does_not_jump_to_default_arguments():
    trees, bank = load_assets(Settings(_env_file=None))
    question = bank.get('py-generator-001')
    point = question.answer_points[-1]
    target = SkillTreeProber(trees['python_backend']).propose(question,
        ScoreResult(3, key_points_missed=(point.point,)), 1, basic=True)
    assert target.node_id.startswith('Python基础/迭代器与生成器')
    assert target.points == (point,)
    assert '可变默认参数' not in target.content


def test_all_new_questions_keep_real_anchors_and_a_valid_route():
    trees, bank = load_assets(Settings(_env_file=None))
    new = [q for q in bank if q.id.endswith('-003')]
    assert len(new) == 12
    for question in new:
        tree = trees[question.position]
        target = SkillTreeProber(tree).propose(question,
            ScoreResult(1, key_points_missed=tuple(p.point for p in question.answer_points)), 1, basic=True)
        assert target.points and len(target.points) == 1
        assert all(p in question.answer_points for p in target.points)
        route = tree.question_routes[question.id]
        assert target.node_id == route or target.node_id.startswith(route + '/')


def test_unmatched_missed_point_stays_on_current_skill_path():
    from app.agent.skill_tree import SkillNode, SkillTree
    from app.domain import AnswerPoint, Question
    root = SkillNode('MySQL')
    root.children = [SkillNode('事务', parent=root), SkillNode('索引', parent=root)]
    question = Question('synthetic', 'java_backend', 'MySQL', 'mid', '复制延迟',
                        (AnswerPoint('复制延迟', ('复制',)),))
    target = SkillTreeProber(SkillTree('java_backend', 'Java', [root])).propose(
        question, ScoreResult(1, key_points_missed=('复制延迟',)), 1)
    assert target.node_id == 'MySQL' and target.points == question.answer_points
    assert '事务' not in target.content


def test_two_concise_explanations_are_not_capped_like_a_keyword_list():
    from app.agent.scorer import HeuristicScorer
    _, bank = load_assets(Settings(_env_file=None))
    question = bank.get('py-sqlite-context-003')
    scorer = HeuristicScorer()
    result = scorer.score(question, '正常退出时提交事务，异常时回滚事务。')
    assert result.score > 3 and result.dimensions['技术深度'] > 6
    assert len(result.key_points_hit) == 2
    assert scorer.score(question, 'commit rollback closing ' * 20).score <= 3
    assert scorer.score(question, '正常退出时commit，正常退出时commit。').score <= 3
