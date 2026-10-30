from dataclasses import asdict, replace
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import delete, func, select, text

from app.agent.score_cache import ScoreCache
from app.agent.scorer import HeuristicScorer, LLMScorer
from app.domain import Question, PlanItem, ScoreOrigin, ScoreRecord, ScoreResult, SandboxResult
from app.models.entities import Interview, QuestionScore, ScoreOriginRecord
from app.repositories import create_interview, save_score_records
from app.score_origin import question_version
from app.services.accounts import attach_owner
from tests.test_accounts import users, auth, resource, owned
from tests.test_ws_recovery import api, answer, connect, receive_turn
from tests.test_scoring_integrity import FakeLLM, ANSWER, payload, question


@pytest.fixture(autouse=True)
def normal_mode(monkeypatch):
    from app.llm import resilience
    monkeypatch.setattr(resilience, "_strict", False)


def test_success_and_cache_keep_independent_origins(question):
    cache = ScoreCache(enabled=True)
    llm = FakeLLM(response=json.dumps(payload()))
    scorer = LLMScorer(llm, cache=cache, model_id="fake-model", config_version="config-1")
    first, second = scorer.score(question, ANSWER), scorer.score(question, ANSWER)
    assert first.origin.source == second.origin.source == "llm"
    assert first.origin.model == "fake-model" and first.origin.config_version == "config-1"
    assert first.origin.prompt_version and len(first.origin.prompt_digest) == 64
    assert not first.origin.cached and second.origin.cached
    assert llm.calls == 1 and first.score == second.score


@pytest.mark.parametrize("exc,reason", [(TimeoutError("do-not-store-secret"), "timeout"), (ValueError("do-not-store-secret"), "bad_payload")])
def test_fallback_is_per_call_and_never_stores_exception_text(question, exc, reason):
    scorer = LLMScorer(FakeLLM(exc=exc), model_id="failed-model", config_version="cfg")
    result = scorer.score(question, ANSWER)
    assert result.origin.source == "heuristic_fallback"
    assert result.origin.fallback_reason == reason and result.origin.scorer_version == HeuristicScorer.VERSION
    assert result.origin.model == "failed-model" and not result.origin.cached
    assert "do-not-store-secret" not in json.dumps(asdict(result.origin))
    assert HeuristicScorer().score(question, ANSWER).origin.source == "heuristic"


@pytest.mark.parametrize("strict,budget", [(True, False), (False, True)])
def test_strict_or_budget_failures_do_not_return_a_fake_origin(question, monkeypatch, strict, budget):
    from app.llm import resilience
    from app.llm.errors import BudgetExceeded, LLMError
    monkeypatch.setattr(resilience, "_strict", strict)
    scorer = LLMScorer(FakeLLM(exc=BudgetExceeded("budget") if budget else ValueError("bad")))
    with pytest.raises(BudgetExceeded if budget else LLMError):
        scorer.score(question, ANSWER)


def test_question_version_changes_with_wording_anchors_and_difficulty(question):
    assert question_version(question) == question_version(replace(question))
    for changed in (replace(question, content="changed"), replace(question, answer_points=()), replace(question, difficulty="hard")):
        assert question_version(changed) != question_version(question)


def test_sandbox_merge_keeps_origin_and_marks_blending(question):
    from app.agent.session import InterviewSession
    from app.agent.state_machine import InterviewState
    from app.rag.question_bank import QuestionBank
    from app.agent.prober import SkillTreeProber
    from app.agent.skill_tree import load_skill_tree
    from app.config import Settings
    tree = load_skill_tree(Settings(_env_file=None).skill_tree_dir)["java_backend"]
    class Judge:
        def judge(self, *args): return SandboxResult(1, 2)
    from app.domain import TestCase as Case
    code = replace(question, is_coding=True, testcases=(Case("", ""),))
    session = InterviewSession(interview_id="sample", position="java_backend", plan=[PlanItem("MySQL", 1, "mid", 1)],
        bank=QuestionBank([code]), scorer=HeuristicScorer(config_version="cfg"), prober=SkillTreeProber(tree), sandbox=Judge())
    session._current = code; session.state = InterviewState.CODING
    result = session._score_answer(ANSWER, code="print(1)")
    assert result.origin.source == "heuristic" and result.origin.config_version == "cfg"
    assert result.origin.sandbox_applied and result.sandbox["objective_score"] == 5


def test_api_turn_persists_origin_and_idempotency_does_not_duplicate_it(users):
    client, factory, a, _ = users
    created = owned(client, a)
    with connect(client, {**created, "access_token": a["access_token"]}) as (socket, snapshot):
        message = answer(snapshot)
        socket.send_json(message); first = receive_turn(socket)
        socket.send_json(message); assert receive_turn(socket) == first
        score = next(event for event in first if event["type"] == "score")
        assert score["scoring_origin"]["source"] == "heuristic"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ScoreOriginRecord)) == 1
        data = db.scalar(select(ScoreOriginRecord.data))
        assert len(data["main_question_version"]) == len(data["question_version"]) == 64
        assert data["question_difficulty"] in ("easy", "mid", "hard")
    path = f'/api/interview/{created["interview_id"]}/report'
    report = client.get(path, headers=resource(a)).json()
    assert report["scoring_sources"] == {"heuristic": 1}
    assert report["per_question"][0]["scoring_origin"] == data
    assert "规则评分" in client.get(path + "/export", headers=resource(a)).text


def add_session(factory, account_id, index, records, *, position="java_backend", status="finished", legacy=False):
    with factory() as db:
        interview = create_interview(db, user_id=None, resume_id=None, position=position,
            difficulty="mid", plan=[PlanItem("MySQL", 1, "mid", 2)], commit=False)
        attach_owner(db, "interview", interview.id, account_id)
        interview.status = status
        interview.ended_at = datetime(2026, 10, 23, 10) + timedelta(minutes=index)
        save_score_records(db, interview.id, records, commit=False)
        db.flush()
        if legacy:
            db.execute(delete(ScoreOriginRecord).where(ScoreOriginRecord.score_id.in_(
                select(QuestionScore.id).where(QuestionScore.interview_id == interview.id))))
        db.commit()
        return interview.id


def record(qid="q", value=8, version="a" * 64, *, theme="MySQL", source="heuristic", cached=False):
    return ScoreRecord(question_id=qid, theme=theme, content="private question",
        result=ScoreResult(value, origin=ScoreOrigin(source=source, scorer_version="v1", cached=cached)),
        answer_text="private answer never returned", main_question_id=qid.split("#p")[0],
        main_question_version=version, question_version=version, question_difficulty="hard", is_coding=False)


def test_review_uses_main_question_weighting_and_omits_private_text(users):
    client, factory, a, b = users
    own_id = add_session(factory, a["account"]["id"], 1, [record("a", 0), record("a#p1", 10, source="llm", cached=True),
        record("a#p2", 10, source="heuristic_fallback"), record("b", 10)])
    add_session(factory, b["account"]["id"], 2, [record(theme="other-account-theme")])
    add_session(factory, a["account"]["id"], 3, [record()], status="running")
    response = client.get("/api/account/review?position=java_backend&theme=MySQL", headers=auth(a))
    assert response.status_code == 200, response.text
    data = response.json(); row = data["items"][0]
    assert data["total"] == data["session_count"] == 1 and row["interview_id"] == own_id
    assert row["score"] == 8.3 and row["question_count"] == 2 and row["answer_count"] == 4
    assert row["repeat_question_count"] == 0
    assert row["scoring_sources"] == {"heuristic": 2, "llm": 1, "heuristic_fallback": 1}
    assert sum(p["cached_count"] for p in row["scoring_profiles"]) == 1
    assert row["question_difficulties"] == {"hard": 2}
    assert "private answer" not in response.text and "private question" not in response.text and "other-account-theme" not in response.text


def test_repeats_require_same_question_version_and_search_beyond_current_page(users):
    client, factory, a, b = users
    account_id = a["account"]["id"]
    first = add_session(factory, account_id, 1, [record()])
    changed = add_session(factory, account_id, 2, [record(version="b" * 64)])
    repeated = add_session(factory, account_id, 3, [record()])
    legacy = add_session(factory, account_id, 4, [record()], legacy=True)
    data = client.get("/api/account/review?limit=1&offset=1", headers=auth(a)).json()
    assert data["total"] == 4 and data["has_more"]
    assert data["items"][0]["interview_id"] == repeated
    assert data["items"][0]["repeat_question_count"] == 1
    changed_row = client.get("/api/account/review?limit=1&offset=2", headers=auth(a)).json()["items"][0]
    assert changed_row["interview_id"] == changed and changed_row["repeat_question_count"] == 0
    old = client.get("/api/account/review?limit=1", headers=auth(a)).json()["items"][0]
    assert old["interview_id"] == legacy and old["unknown_question_version_count"] == 1
    assert old["scoring_sources"] == {"unknown": 1} and old["repeat_question_count"] == 0
    assert client.get("/api/account/review", headers=auth(b)).json()["total"] == 0
    legacy_report = client.get(f"/api/interview/{legacy}/report", headers=resource(a)).json()
    assert legacy_report["per_question"][0]["scoring_origin"]["source"] == "unknown"


def test_review_filters_position_theme_and_excludes_unclaimed_sessions(users):
    client, factory, a, _ = users
    add_session(factory, a["account"]["id"], 1, [record(theme="MySQL")])
    python_id = add_session(factory, a["account"]["id"], 2, [record(theme="Python基础")], position="python_backend")
    with factory() as db:
        create_interview(db, user_id=None, resume_id=None, position="extra-unclaimed", difficulty="mid", plan=[])
    data = client.get("/api/account/review?position=python_backend&theme=Python基础", headers=auth(a)).json()
    assert data["total"] == 1 and data["items"][0]["interview_id"] == python_id
    assert {p["id"] for p in data["positions"]} == {"java_backend", "python_backend"}
    assert client.get("/api/account/review?position=java_backend&theme=Python基础", headers=auth(a)).json()["total"] == 0
    assert client.get("/api/account/review?limit=51", headers=auth(a)).status_code == 422
    assert client.get("/api/account/review").status_code == 401


def test_origin_is_removed_with_record_under_foreign_keys(users):
    client, factory, a, _ = users
    item = add_session(factory, a["account"]["id"], 1, [record()])
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON")); db.commit()
    assert client.delete(f"/api/account/interviews/{item}", headers=auth(a)).status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ScoreOriginRecord)) == 0
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert client.get("/api/account/review", headers=auth(a)).json()["total"] == 0
