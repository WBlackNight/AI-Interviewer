import json
import math
from dataclasses import replace

import pytest
from pydantic import ValidationError
from app.agent.planner import HeuristicPlanner, LLMPlanner
from app.agent.prober import LLMProber
from app.agent.scorer import LLMScorer, HeuristicScorer
from app.agent.score_schema import ScorePayload, build_score_result
from app.config import Settings
from app.domain import Question, ResumeData, ScoreResult
from app.factories import load_assets
from app.rag.resume_parser import parse_resume_text
from app.security import sanitize_pii


class FakeLLM:
    def __init__(self, data):
        self.data, self.calls = data, []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return json.dumps(self.data, ensure_ascii=False)


@pytest.fixture
def assets():
    return load_assets(Settings(_env_file=None))


def test_heuristic_weights_and_empty_bank(assets):
    from app.rag.question_bank import QuestionBank
    trees, bank = assets
    planner = HeuristicPlanner(trees['java_backend'])
    kwargs = dict(position='java_backend', difficulty='mid',
                  resume=ResumeData(skills=['MySQL', 'Redis']), max_themes=3)
    plan = planner.build_plan(bank=bank, **kwargs)
    assert sum(p.weight for p in plan) == pytest.approx(1)
    assert plan[0].theme in ('MySQL', 'Redis')
    assert plan[0].weight > plan[-1].weight
    assert planner.build_plan(bank=QuestionBank([]), **kwargs) == []


def test_llm_planner_really_calls_and_normalizes(assets):
    trees, bank = assets
    fake = FakeLLM({'plan': [dict(theme='MySQL', weight=0.6, difficulty='hard',
        question_count=2, include_coding=True), dict(theme='Redis', weight=0.2,
        difficulty='mid', question_count=1, include_coding=False)]})
    plan = LLMPlanner(fake, trees['java_backend']).build_plan(position='java_backend',
        difficulty='mid', resume=ResumeData(), bank=bank, max_themes=3)
    assert len(fake.calls) == 1
    assert fake.calls[0][1]['json_mode']
    assert plan[0].difficulty == 'hard' and plan[0].weight == pytest.approx(0.75)


@pytest.mark.parametrize('field,value', [('weight', math.nan), ('weight', -1),
    ('difficulty', 'invalid'), ('question_count', 0), ('question_count', True),
    ('include_coding', 'false'), ('theme', '算法与编码')])
def test_illegal_plan_falls_back(assets, field, value, caplog):
    trees, bank = assets
    item = dict(theme='MySQL', weight=1, difficulty='mid', question_count=1, include_coding=False)
    item[field] = value
    fake = FakeLLM({'plan': [item]})
    plan = LLMPlanner(fake, trees['java_backend']).build_plan(position='java_backend',
        difficulty='mid', resume=ResumeData(), bank=bank, max_themes=3)
    assert len(fake.calls) == 1
    assert sum(p.weight for p in plan) == pytest.approx(1)
    assert 'component=planner' in caplog.text


def score_input(q, answer):
    return {'score': 8, 'dimensions': {'技术深度': 8, '表达逻辑': 8, '岗位匹配': 8},
            'key_points_hit': [p.point for p in q.answer_points], 'key_points_missed': [],
            # 正例要为所有声明命中的锚点提供原文，不能只引用前20字。
            'evidence': '引用实际回答', 'evidence_quotes': [answer]}


@pytest.mark.parametrize('mutation', ['negative', 'nan', 'missing_dim', 'fake_anchor',
    'overlap', 'missing_evidence', 'fake_quote', 'wrong_list', 'empty_answer'])
def test_score_contract_rejects_bad_output(assets, mutation):
    _, bank = assets
    q = bank.get('jv-mysql-index-001')
    answer = 'B+树具有有序叶节点链表，支持范围扫描，较矮的树减少磁盘页读取。'
    data = score_input(q, answer)
    if mutation == 'negative': data['dimensions']['技术深度'] = -3
    if mutation == 'nan': data['dimensions']['技术深度'] = math.nan
    if mutation == 'missing_dim': del data['dimensions']['技术深度']
    if mutation == 'fake_anchor': data['key_points_hit'].append('不存在的锚点')
    if mutation == 'overlap': data['key_points_missed'] = data['key_points_hit'][:1]
    if mutation == 'missing_evidence': data['evidence'] = ''
    if mutation == 'fake_quote': data['evidence_quotes'] = ['候选人没有说过的话']
    if mutation == 'wrong_list': data['key_points_hit'] = '字符串'
    if mutation == 'empty_answer': answer = ''
    # P2 步骤 2.2：校验逻辑从 LLMScorer._validate 抽到 score_schema，
    # 契约不变（非法载荷必须被拒绝），只是调用点跟着实现走。
    with pytest.raises((ValueError, KeyError, TypeError)):
        build_score_result(ScorePayload.model_validate(data), q, answer)


def test_valid_llm_score_and_observable_fallback(assets, caplog):
    _, bank = assets
    q = bank.get('jv-mysql-index-001')
    answer = 'B+树是多路搜索树，叶子用链表连接，支持范围查询，树高决定磁盘IO。'
    fake = FakeLLM(score_input(q, answer))
    result = LLMScorer(fake).score(q, answer)
    assert result.score == 8 and answer[:20] in result.evidence
    fake.data['evidence_quotes'] = ['伪造']
    result = LLMScorer(fake).score(q, answer)
    baseline = HeuristicScorer().score(q, answer)
    assert replace(result, origin=baseline.origin) == baseline
    assert result.origin.source == "heuristic_fallback" and result.origin.fallback_reason == "bad_payload"
    assert 'component=scorer' in caplog.text


def test_keyword_refusal_and_stuffing(assets):
    _, bank = assets
    q = bank.get('jv-mysql-index-001')
    assert HeuristicScorer().score(q, '我不会B+树，也不知道范围查询和磁盘IO').score < 4
    assert HeuristicScorer().score(q, 'b+树 哈希 范围 叶子 磁盘 链表 ' * 30).score <= 3


def test_skill_paths_and_exhausted_questions(assets):
    trees, bank = assets
    tree = trees['java_backend']
    assert tree.find('锁') is None
    assert tree.find('MySQL/锁').parent.name == 'MySQL'
    assert tree.find('并发编程/锁').parent.name == '并发编程'
    asked = {q.id for q in bank}
    assert bank.next_question(position='java_backend', theme='MySQL', difficulty='easy', exclude=asked) is None
    assert bank.next_coding_question(position='java_backend', exclude=asked) is None


def test_structured_probe_uses_answer_and_rejects_wrong_node(assets, caplog):
    trees, bank = assets
    tree = trees['java_backend']
    q = bank.get('jv-mysql-index-001')
    fake = FakeLLM({'node_id': 'JVM', 'content': '无关追问'})
    prober = LLMProber(fake, tree)
    result = prober.propose(q, ScoreResult(3, key_points_missed=tuple(p.point for p in q.answer_points)),
                           1, answer='实际回答全文')
    assert result.node_id.startswith('MySQL/')
    assert '实际回答全文' in fake.calls[0][0][1]['content']
    assert 'component=prober' in caplog.text
    child = prober._fallback.propose(q, ScoreResult(3), 2, node_id=result.node_id)
    assert child.node_id == result.node_id or child.node_id.startswith(result.node_id + '/')
    assert all(point in q.answer_points for point in child.points)


@pytest.mark.parametrize('kwargs', [{'pass_score': float('nan')}, {'pass_score': 11},
    {'probe_score': 8, 'pass_score': 7}, {'probe_depth_limit': -1}, {'max_plan_themes': 0}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


def test_empty_education_and_basic_pii():
    assert parse_resume_text('').education == ''
    text = '手机号13812345678 邮箱abc@example.com 身份证110101199001011234'
    assert sanitize_pii(text) == '手机号[PHONE] 邮箱[EMAIL] 身份证[ID]'


def test_resume_llm_validation_and_redaction(caplog):
    from app.rag.resume_parser import parse_resume_text_with_llm
    fake = FakeLLM({'skills': ['Java'], 'projects': ['联系13812345678'], 'education': ''})
    result = parse_resume_text_with_llm('专业技能\nJava\n项目经历\n联系人13812345678', fake)
    assert '13812345678' not in fake.calls[0][0][1]['content']
    assert result.projects == ['联系[PHONE]']
    fake.data['skills'] = 'Java'
    result = parse_resume_text_with_llm('专业技能\nJava', fake)
    assert result.skills == ['Java'] and 'component=resume' in caplog.text


def test_snapshot_restores_strategy_and_rejects_changed_assets(assets):
    from app.agent.session import InterviewSession, AssetVersionError
    from app.agent.prober import SkillTreeProber
    from app.domain import PlanItem
    from app.rag.question_bank import QuestionBank
    trees, bank = assets
    kwargs = dict(interview_id='test', position='java_backend',
        plan=[PlanItem('MySQL', 1, 'mid', 1)], bank=bank, scorer=HeuristicScorer(),
        prober=SkillTreeProber(trees['java_backend']), pass_score=8, probe_score=6)
    first = InterviewSession(**kwargs)
    first.start()
    saved = first.snapshot()
    second = InterviewSession(**{**kwargs, 'pass_score': 7, 'probe_score': 4})
    second.restore(saved)
    assert second.pass_score == 8 and second.probe_score == 6
    assert second.current_question == first.current_question
    changed = QuestionBank([replace(q, content=q.content + '修改') for q in bank])
    with pytest.raises(AssetVersionError):
        InterviewSession(**{**kwargs, 'bank': changed}).restore(saved)
