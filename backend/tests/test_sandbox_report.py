import base64
import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain import TestCase as Case, ScoreRecord, ScoreResult, PlanItem
from app.models.entities import Base
from app.repositories import create_interview, save_score_records, commit_turn, ConcurrentTurnError, load_scores, seed_questions
from app.sandbox.judge0 import Judge0Sandbox, SandboxUnavailable
from app.services.report import build_report


def sandbox(monkeypatch, statuses, *, timeout=1):
    requests = []
    original = httpx.Client
    def respond(request):
        requests.append(request)
        if request.method == 'POST':
            return httpx.Response(201, json={'token': 'fake-token'})
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        if status == 'http_error':
            return httpx.Response(503)
        return httpx.Response(200, json={'status': {'id': status, 'description': str(status)},
            'stdout': base64.b64encode('[0, 1]'.encode()).decode()})
    monkeypatch.setattr('app.sandbox.judge0.httpx.Client',
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    return Judge0Sandbox('http://fake', timeout=timeout, poll_interval=0), requests


def test_sandbox_polls_and_sends_correct_limits(monkeypatch):
    judge, requests = sandbox(monkeypatch, [1, 2, 3])
    result = judge.judge('print([0, 1])', [Case('2 7\n9', '[0, 1]')])
    assert result.passed == result.total == 1 and len(requests) == 4
    assert requests[0].url.params['base64_encoded'] == 'true'
    assert requests[0].url.params['wait'] == 'false'
    data = json.loads(requests[0].content)
    assert base64.b64decode(data['source_code']) == b'print([0, 1])'
    assert not data['enable_network'] and data['wall_time_limit'] == 5


@pytest.mark.parametrize('status', [4, 5, 6])
def test_candidate_failure_is_scored(monkeypatch, status):
    judge, _ = sandbox(monkeypatch, [status])
    result = judge.judge('bad code', [Case('', '')])
    assert result.passed == 0 and result.detail[0]['status'] == str(status)


@pytest.mark.parametrize('status', [13, 14, 99, 'http_error'])
def test_infrastructure_failure_is_not_zero_score(monkeypatch, status):
    judge, _ = sandbox(monkeypatch, [status])
    with pytest.raises(SandboxUnavailable):
        judge.judge('print(1)', [Case('', '')])


def test_code_byte_limit_and_timeout(monkeypatch):
    judge, _ = sandbox(monkeypatch, [1], timeout=0.005)
    with pytest.raises(ValueError):
        judge.judge('中' * 6000, [Case('', '')])
    with pytest.raises(SandboxUnavailable):
        judge.judge('print(1)', [Case('', '')])


def test_report_counts_weighting_and_absolute_weakness():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        interview = create_interview(db, user_id=None, resume_id=None, position='java_backend',
            difficulty='mid', plan=[PlanItem('MySQL', .8, 'mid', 1), PlanItem('Redis', .2, 'mid', 1)])
        values = [('a', 'MySQL', 0), ('a#p1', 'MySQL', 10), ('a#p2', 'MySQL', 10), ('b', 'Redis', 10)]
        records = [ScoreRecord(q, theme, '实际题干', ScoreResult(score,
            dimensions={k: score for k in ('技术深度', '表达逻辑', '岗位匹配')}),
            probe_depth=1 if '#p' in q else 0, answer_text='实际回答') for q, theme, score in values]
        save_score_records(db, interview.id, records)
        report = build_report(db, interview, None)
        assert report['question_count'] == 2 and report['answer_count'] == 4
        assert report['overall'] == 7.3 and report['weak_points'] == ['MySQL']
        assert not report['is_complete']
        for row in load_scores(db, interview.id):
            row.score = 10
        db.commit()
        assert build_report(db, interview, None)['weak_points'] == []
    engine.dispose()


def test_seed_updates_same_id_and_health_uses_active_assets():
    from dataclasses import replace
    from app.domain import Question
    from app.models.entities import Question as QuestionORM
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        q = Question('q', 'java_backend', 'MySQL', 'mid', '旧题干')
        assert seed_questions(db, [q]) == 1
        assert seed_questions(db, [replace(q, content='新题干')]) == 0
        assert db.get(QuestionORM, 'q').content == '新题干'
    engine.dispose()


def test_compare_and_swap_rejects_lost_update():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        interview = create_interview(db, user_id=None, resume_id=None, position='java_backend',
            difficulty='mid', plan=[PlanItem('MySQL', 1, 'mid', 1)])
        commit_turn(db, interview.id, 0, {'finished': False}, [{'type': 'state'}], [])
        with pytest.raises(ConcurrentTurnError):
            commit_turn(db, interview.id, 0, {'finished': True}, [{'type': 'closing'}], [])
        db.rollback()
    engine.dispose()
