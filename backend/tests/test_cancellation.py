import pytest
from sqlalchemy import delete, func, select, update

from app.models.entities import (Interview, InterviewEvent, InterviewRuntime, InterviewSubmission,
    QuestionScore, ScoreOriginRecord, LLMBudgetUsage)
from app.repositories import cancel_interview, commit_turn, ConcurrentTurnError
from app.schemas import AnswerMessage
from tests.test_accounts import users, auth, resource, owned, PASSWORD
from tests.test_ws_recovery import api, create, connect, answer, receive_turn


def path(item):
    return f'/api/interview/{item["interview_id"]}/cancel'


def test_cancel_requires_resource_or_owner_and_is_idempotent(users, monkeypatch):
    from app.api import routes
    client, factory, a, b = users
    item = owned(client, a)
    monkeypatch.setattr(routes, "load_assets", lambda *a: pytest.fail("取消不能加载题库或模型"))
    assert client.post(path(item)).status_code == 403
    assert client.post(path(item), headers=resource(b)).status_code == 403
    first = client.post(path(item), headers=resource(a)).json()
    second = client.post(path(item), headers=resource(a)).json()
    assert first["status"] == second["status"] == "cancelled"
    assert first["changed"] and not second["changed"] and first["version"] == second["version"] == 1
    with factory() as db:
        assert db.get(Interview, item["interview_id"]).status == "cancelled"
        assert db.scalar(select(func.count()).select_from(InterviewEvent)) == 1
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 0


def test_anonymous_can_cancel_and_read_partial_report(api):
    client, _ = api
    item = create(client)
    headers = {"X-Interview-Token": item["access_token"]}
    assert client.post(path(item), headers=headers).status_code == 200
    base = f'/api/interview/{item["interview_id"]}'
    report = client.get(base + "/report", headers=headers).json()
    assert report["is_terminal"] and report["is_cancelled"] and not report["is_complete"]
    assert report["answer_count"] == 0 and report["overall"] is None
    assert report["practice_themes"] == []
    assert "已取消（部分报告）" in client.get(base + "/report/export", headers=headers).text
    assert client.post(base + "/practice", headers=headers).status_code == 409


def test_running_cancel_keeps_committed_answer_and_terminal_reconnect(users, monkeypatch):
    from app.api import ws
    client, factory, a, _ = users
    item = owned(client, a); signed = {**item, "access_token": a["access_token"]}
    with connect(client, signed) as (socket, snapshot):
        message = answer(snapshot)
        socket.send_json(message); assert receive_turn(socket)[-1]["type"] == "question"
    assert client.post(path(item), headers=resource(a)).status_code == 200
    monkeypatch.setattr(ws, "load_session", lambda *a: pytest.fail("已取消快照不能恢复Agent或加载资产"))
    with connect(client, signed) as (_, snapshot):
        assert snapshot["cancelled"] and snapshot["finished"] and snapshot["current_question"] is None
        assert sum(e["type"] == "score" for e in snapshot["events"]) == 1
    # 已提交消息重放也必须返回终态，不能重放旧问题并让界面恢复作答。
    assert ws.process_message(item["interview_id"], AnswerMessage(**message), a["access_token"])[0]["cancelled"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 1
        assert db.scalar(select(func.count()).select_from(ScoreOriginRecord)) == 1
    report = client.get(f'/api/interview/{item["interview_id"]}/report', headers=resource(a)).json()
    assert report["answer_count"] == 1 and not report["is_complete"]
    assert client.get("/api/account/review", headers=auth(a)).json()["total"] == 0
    assert client.delete(f'/api/account/interviews/{item["interview_id"]}', headers=auth(a)).status_code == 200


def test_existing_socket_receives_terminal_before_processing_more_input(users):
    client, factory, a, _ = users
    item = owned(client, a)
    with connect(client, {**item, "access_token": a["access_token"]}) as (socket, snapshot):
        assert client.post(path(item), headers=resource(a)).status_code == 200
        socket.send_json(answer(snapshot))
        terminal = socket.receive_json()
        assert terminal["type"] == "snapshot" and terminal["cancelled"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 0


def test_cancel_during_scoring_discards_result_but_preserves_budget(users, monkeypatch):
    from app.api import ws
    client, factory, a, _ = users
    item = owned(client, a)
    with factory() as db:
        db.add(LLMBudgetUsage(resource_kind="interview", resource_id=item["interview_id"], policy={}, used_tokens=42,
                             unknown_calls=1, pending="pending-call")); db.commit()
    original = ws.build_scorer
    def build(*args):
        scorer = original(*args); score = scorer.score
        def cancelled_score(*args):
            result = score(*args)
            with factory() as db:
                cancel_interview(db, db.get(Interview, item["interview_id"]))
            return result
        scorer.score = cancelled_score
        return scorer
    monkeypatch.setattr(ws, "build_scorer", build)
    with connect(client, {**item, "access_token": a["access_token"]}) as (socket, snapshot):
        socket.send_json(answer(snapshot))
        result = socket.receive_json()
        assert result["type"] == "snapshot" and result["cancelled"]
    with factory() as db:
        for model in (QuestionScore, ScoreOriginRecord, InterviewSubmission):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        runtime = db.get(InterviewRuntime, item["interview_id"])
        assert runtime.version == 2
        meter = db.get(LLMBudgetUsage, ("interview", item["interview_id"]))
        assert meter.used_tokens == 42 and meter.pending == "pending-call" and meter.unknown_calls == 1


@pytest.mark.parametrize("broken", ["asset", "snapshot", "legacy"])
def test_cancel_does_not_depend_on_restorable_assets_or_snapshot(users, broken):
    client, factory, a, _ = users
    item = owned(client, a)
    with connect(client, {**item, "access_token": a["access_token"]}):
        pass
    with factory() as db:
        runtime = db.get(InterviewRuntime, item["interview_id"])
        if broken == "asset": runtime.snapshot = {**runtime.snapshot, "asset_version": "old-assets"}
        elif broken == "snapshot": runtime.snapshot = ["invalid-snapshot"]
        else: db.delete(runtime)
        db.commit()
    assert client.post(path(item), headers=resource(a)).status_code == 200
    with connect(client, {**item, "access_token": a["access_token"]}) as (_, snapshot):
        assert snapshot["cancelled"]
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200


def test_legacy_single_event_zero_sequence_is_preserved(api):
    client, factory = api
    item = create(client)
    with factory() as db:
        db.execute(delete(InterviewRuntime).where(InterviewRuntime.interview_id == item["interview_id"]))
        db.get(Interview, item["interview_id"]).status = "running"
        db.add(InterviewEvent(interview_id=item["interview_id"], seq=0, type="greeting", payload={"type": "greeting", "text": "旧事件"}))
        db.commit()
    assert client.post(path(item), headers={"X-Interview-Token": item["access_token"]}).status_code == 200
    with factory() as db:
        assert list(db.scalars(select(InterviewEvent.seq).order_by(InterviewEvent.seq))) == [0, 1]


def test_finished_cannot_be_reclassified_as_cancelled(users):
    client, factory, a, _ = users
    item = owned(client, a)
    with factory() as db:
        db.get(Interview, item["interview_id"]).status = "finished"; db.commit()
    assert client.post(path(item), headers=resource(a)).status_code == 409
    with factory() as db:
        assert db.get(Interview, item["interview_id"]).status == "finished"
        assert db.scalar(select(func.count()).select_from(InterviewEvent)) == 0


def test_cancelled_runtime_rejects_both_old_and_new_version_commits(api):
    client, factory = api
    item = create(client)
    client.post(path(item), headers={"X-Interview-Token": item["access_token"]})
    for version in (0, 1):
        with factory() as db:
            with pytest.raises(ConcurrentTurnError):
                commit_turn(db, item["interview_id"], version, {"finished": False}, [], [])
    with factory() as db:
        assert db.get(Interview, item["interview_id"]).status == "cancelled"


def test_cancel_is_atomic_when_runtime_has_changed(api):
    client, factory = api; item = create(client)
    with factory() as db:
        row = db.get(Interview, item["interview_id"])
        db.get(InterviewRuntime, row.id)
        # 保留旧ORM视图，模拟读取后另一个轮次推进了数据库版本。
        stale = db.get(InterviewRuntime, row.id)
        db.execute(update(InterviewRuntime).where(InterviewRuntime.interview_id == row.id).values(version=1),
                   execution_options={"synchronize_session": False})
        assert stale.version == 0
        with pytest.raises(ConcurrentTurnError): cancel_interview(db, row)
        db.rollback()
    with factory() as db:
        assert db.get(Interview, item["interview_id"]).status == "created"
        assert db.scalar(select(func.count()).select_from(InterviewEvent)) == 0
