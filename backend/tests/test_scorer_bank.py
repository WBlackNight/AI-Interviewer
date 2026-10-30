"""评分器与题库单元测试：确定性保证。"""
from __future__ import annotations

from pathlib import Path
import pytest

from app.agent.scorer import HeuristicScorer
from app.domain import Question
from app.rag.question_bank import QuestionBank

BANK_DIR = Path(__file__).resolve().parents[2] / "data" / "question_bank"


def _q() -> Question:
    return Question.from_dict(
        {
            "id": "t-1",
            "position": "java_backend",
            "theme": "MySQL",
            "difficulty": "mid",
            "content": "测试题",
            "answer_points": [
                {"point": "要点A", "keywords": ["b+树"]},
                {"point": "要点B", "keywords": ["mvcc"]},
            ],
        }
    )


class TestHeuristicScorer:
    def setup_method(self):
        self.scorer = HeuristicScorer()

    def test_full_hit_passes_threshold(self):
        result = self.scorer.score(
            _q(),
            "B+树 是多路平衡树，查询走 索引，同时 MVCC 提供快照读，" + "补充内容 " * 30,
        )
        assert result.score >= 7.0
        assert result.key_points_hit == ("要点A", "要点B")
        assert result.key_points_missed == ()
        assert "要点A" in result.evidence

    def test_no_hit_fails(self):
        result = self.scorer.score(_q(), "不会")
        assert result.score < 4.0
        assert result.key_points_hit == ()

    def test_partial_hit_in_between(self):
        result = self.scorer.score(_q(), "b+树" + "内容" * 60)
        assert 0 < result.score < 10
        assert result.key_points_hit == ("要点A",)
        assert result.key_points_missed == ("要点B",)

    def test_deterministic(self):
        answer = "b+树 与 mvcc 都讲到了，" + "细节 " * 40
        assert self.scorer.score(_q(), answer) == self.scorer.score(_q(), answer)

    def test_score_capped_at_10(self):
        result = self.scorer.score(
            _q(), "b+树 mvcc b+树 mvcc " + "非常充实的内容 " * 100
        )
        assert result.score <= 10.0


class TestQuestionBank:
    def test_load_real_bank(self):
        bank = QuestionBank.load(BANK_DIR)
        assert len(bank) >= 10
        assert bank.has_coding("java_backend")

    def test_next_question_excludes_asked(self):
        bank = QuestionBank.load(BANK_DIR)
        q1 = bank.next_question(
            position="java_backend", theme="MySQL", difficulty="mid", exclude=set()
        )
        assert q1 is not None
        q2 = bank.next_question(
            position="java_backend",
            theme="MySQL",
            difficulty="mid",
            exclude={q1.id},
        )
        assert q2 is not None
        assert q2.id != q1.id

    def test_next_question_unknown_theme_returns_none(self):
        bank = QuestionBank.load(BANK_DIR)
        assert (
            bank.next_question(
                position="java_backend", theme="不存在的主题", difficulty="mid", exclude=set()
            )
            is None
        )

    def test_coding_question_retrieval(self):
        bank = QuestionBank.load(BANK_DIR)
        q = bank.next_coding_question(position="java_backend", exclude=set())
        assert q is not None and q.is_coding and q.testcases


@pytest.mark.parametrize('answer,hit', [
    ('调用后得到协程对象，不会自动调度执行。', True),
    ('协程对象不会因此自动调度执行。', True),
    ('协程对象不会 自动调度执行。', True),
    ('我不会协程对象', False),
    ('协程对象我不会', False),
    ('协程对象不会用', False),
    ('我不太清楚协程对象', False),
    ('没做过协程对象的练习', False),
    ('协程对象不会自动执行，但我不懂原理。', False),
    ('我不知道。协程对象不会自动执行。', True),
    ('我不会;协程对象需要调度才能运行。', True),
])
def test_abstention_and_automatic_execution_have_distinct_meanings(answer, hit):
    question = Question.from_dict({
        'id': 'async-check', 'position': 'python_backend', 'theme': '异步与并发',
        'difficulty': 'easy', 'content': '协程怎样开始执行？',
        'answer_points': [{'point': '返回协程对象，需要安排执行', 'keywords': ['协程对象']}],
    })
    result = HeuristicScorer().score(question, answer)
    assert bool(result.key_points_hit) is hit
    assert result.origin.scorer_version == 'heuristic-v3'


@pytest.mark.parametrize('keyword', ['不会', '不能', '不是', '没有'])
def test_negation_word_alone_is_not_knowledge_evidence(keyword):
    question = Question.from_dict({
        'id': 'negative-check', 'position': 'python_backend', 'theme': '异步与并发',
        'difficulty': 'easy', 'content': '请解释运行机制',
        'answer_points': [{'point': '需要解释机制', 'keywords': [keyword]}],
    })
    result = HeuristicScorer().score(question, '文件不会自动生成，不能简单重试，不是没有条件。')
    assert result.key_points_hit == ()


def test_candidate_coroutine_complete_and_partial_are_not_abstentions():
    import json
    root = Path(__file__).resolve().parents[2]
    bank = QuestionBank.load(root / 'data/question_candidates')
    question = bank.get('py-coroutine-start-002')
    cases = [json.loads(line) for line in (root / 'data/evals/candidate_answer_cases.jsonl')
             .read_text(encoding='utf-8').splitlines()]
    for case in cases:
        if case['question_id'] == question.id:
            result = HeuristicScorer().score(question, case['answer'])
            assert set(result.key_points_hit) == set(case['expected_hits'])


@pytest.mark.parametrize('answer,hit', [
    ('协程对象不会自动作为任务调度执行。', False),
    ('协程对象不会因此自动创建任务。', False),
    ('任务需要显式创建，协程对象不会自动调度。', True),
    ('协程对象不会自动调度，create_task可以创建任务。', True),
])
def test_automatic_negation_does_not_award_objects_inside_its_scope(answer, hit):
    question = Question.from_dict({
        'id': 'task-check', 'position': 'python_backend', 'theme': '异步与并发',
        'difficulty': 'easy', 'content': '怎样创建任务？',
        'answer_points': [{'point': '描述任务创建', 'keywords': ['任务']}],
    })
    assert bool(HeuristicScorer().score(question, answer).key_points_hit) is hit
