import pytest
from sqlalchemy import event, func, select, text

from app.models.entities import (Interview, InterviewRuntime, ResourceOwner, RevisionPractice, RevisionTask,
                                 QuestionScore, AccessGrant, AccountSession)
from app.services.accounts import now_utc, token_hash
from datetime import timedelta
from tests.test_accounts import users, auth, resource, PASSWORD
from tests.test_ws_recovery import api, connect, answer, receive_turn
from tests.test_revision_tasks import source, add


@pytest.fixture(autouse=True)
def offline_settings(monkeypatch):
    from app.api import accounts, routes
    monkeypatch.setattr(accounts, "get_settings", lambda: routes.settings)


def start(client, user, task_id):
    return client.post(f"/api/account/revision-tasks/{task_id}/practice", headers=auth(user))


def task_for(client, factory, user, **kwargs):
    sid = source(factory, user, **kwargs)
    task = add(client, user, sid).json()["items"][0]
    return sid, task


@pytest.mark.parametrize("position,theme", [("java_backend", "MySQL"), ("python_backend", "Python基础")])
def test_practice_uses_only_task_scope_and_source_difficulty_without_model_or_answer_copy(users, monkeypatch, position, theme):
    from app.api import routes
    client, factory, a, b = users
    sid, task = task_for(client, factory, a, position=position, theme=theme)
    with factory() as db:
        db.get(Interview, sid).difficulty = "hard"
        db.commit()
    monkeypatch.setattr(routes, "build_llm", lambda *args: pytest.fail("任务专项不应调用规划模型"))
    result = client.post(f'/api/account/revision-tasks/{task["id"]}/practice', headers=auth(a),
        json={"position": "other", "themes": ["forged"], "status": "done"})
    assert result.status_code == 200, result.text
    child = result.json()
    assert child["position"] == position and child["revision_task_id"] == task["id"] and not child["reused"]
    assert child["account_owned"] and child["access_token"] is None
    assert len(child["plan"]) == 1 and child["plan"][0]["theme"] == theme
    assert child["plan"][0]["difficulty"] == "hard" and 1 <= child["plan"][0]["question_count"] <= 2
    assert not child["plan"][0]["include_coding"]
    with factory() as db:
        row = db.get(Interview, child["interview_id"])
        assert row.resume_id is None and row.user_id is None
        assert db.get(ResourceOwner, ("interview", row.id)).account_id == a["account"]["id"]
        assert db.scalar(select(func.count()).select_from(QuestionScore).where(QuestionScore.interview_id == row.id)) == 0
        assert db.get(AccessGrant, ("interview", row.id)) is None
        assert db.scalar(select(RevisionPractice.task_id)) == task["id"]
    assert client.get(f'/api/interview/{child["interview_id"]}/report', headers=resource(b)).status_code == 403


def test_duplicate_created_and_running_requests_reuse_one_interview(users, monkeypatch):
    from app.services import revision
    client, factory, a, _ = users
    sid, task = task_for(client, factory, a)
    child = start(client, a, task["id"]).json()
    monkeypatch.setattr(revision, "load_assets", lambda *args: pytest.fail("继续旧专项不应重新生成大纲"))
    repeated = start(client, a, task["id"]).json()
    assert repeated["reused"] and repeated["interview_id"] == child["interview_id"]
    with connect(client, {**child, "access_token": a["access_token"]}) as (_, state):
        assert state["current_question"]["theme"] == "MySQL"
    assert start(client, a, task["id"]).json()["interview_id"] == child["interview_id"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 2
        assert db.scalar(select(func.count()).select_from(RevisionPractice)) == 1


def test_finished_and_cancelled_practice_allow_new_sessions_without_changing_manual_progress(users):
    client, factory, a, _ = users
    sid, task = task_for(client, factory, a)
    completed = client.patch(f'/api/account/revision-tasks/{task["id"]}', json={"status": "done"}, headers=auth(a)).json()
    first = start(client, a, task["id"]).json()
    with factory() as db:
        db.get(Interview, first["interview_id"]).status = "finished"
        db.commit()
    second = start(client, a, task["id"]).json()
    assert not second["reused"] and second["interview_id"] != first["interview_id"]
    assert client.post(f'/api/interview/{second["interview_id"]}/cancel', headers=resource(a)).status_code == 200
    third = start(client, a, task["id"]).json()
    assert not third["reused"] and third["interview_id"] not in {first["interview_id"], second["interview_id"]}
    saved = client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]
    assert saved["status"] == "done" and saved["completed_at"] == completed["completed_at"]
    assert saved["latest_practice"] == {"interview_id": third["interview_id"], "status": "created"}


def test_reconnect_answer_and_report_keep_source_and_do_not_complete_task(users):
    client, factory, a, _ = users
    sid, task = task_for(client, factory, a)
    child = start(client, a, task["id"]).json()
    credentials = {**child, "access_token": a["access_token"]}
    with connect(client, credentials) as (socket, state):
        socket.send_json(answer(state)); assert receive_turn(socket)[-1]["type"] == "question"
    with connect(client, credentials) as (_, restored):
        assert restored["current_question"]["theme"] == "MySQL"
    path = f'/api/interview/{child["interview_id"]}/report'
    report = client.get(path, headers=resource(a)).json()
    assert report["answer_count"] == 1
    assert report["revision_source"] == {"task_id": task["id"], "interview_id": sid, "theme": "MySQL"}
    assert client.get(path + "/export?format=json", headers=resource(a)).json() == report
    assert "复习任务来源" in client.get(path + "/export", headers=resource(a)).text
    assert client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]["status"] == "todo"


@pytest.mark.parametrize("position,theme", [("java_backend", "已移除主题"), ("java_backend", "算法与编码"), ("retired_position", "MySQL"), ("python_backend", "MySQL")])
def test_retired_cross_position_or_coding_topic_never_broadens_into_general_interview(users, position, theme):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a, position=position, theme=theme)
    result = start(client, a, task["id"])
    assert result.status_code == 422, result.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 1
        assert db.scalar(select(func.count()).select_from(RevisionPractice)) == 0


def test_unknown_other_expired_or_deleted_task_is_rejected(users):
    client, factory, a, b = users
    sid, task = task_for(client, factory, a)
    assert client.post(f'/api/account/revision-tasks/{task["id"]}/practice').status_code == 401
    assert start(client, b, task["id"]).status_code == 404
    assert start(client, a, "missing").status_code == 404
    with factory() as db:
        db.get(AccountSession, token_hash(b["access_token"])).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert start(client, b, task["id"]).status_code == 401
    client.delete(f"/api/account/interviews/{sid}", headers=auth(a))
    assert start(client, a, task["id"]).status_code == 404


def test_deleting_source_detaches_but_preserves_independent_practice_with_foreign_keys(users):
    client, factory, a, _ = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
    sid, task = task_for(client, factory, a)
    child = start(client, a, task["id"]).json()
    assert client.delete(f"/api/account/interviews/{sid}", headers=auth(a)).status_code == 200
    report = client.get(f'/api/interview/{child["interview_id"]}/report', headers=resource(a))
    assert report.status_code == 200 and report.json()["revision_source"] is None
    with factory() as db:
        assert db.get(Interview, child["interview_id"]) is not None
        assert db.get(RevisionTask, task["id"]) is None
        assert db.scalar(select(func.count()).select_from(RevisionPractice)) == 0
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_deleting_child_updates_latest_and_deleting_account_removes_all_links(users):
    client, factory, a, b = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
    _, task = task_for(client, factory, a)
    child = start(client, a, task["id"]).json()
    assert client.delete(f'/api/account/interviews/{child["interview_id"]}', headers=auth(a)).status_code == 200
    assert client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]["latest_practice"] is None
    start(client, a, task["id"])
    _, other_task = task_for(client, factory, b)
    other = start(client, b, other_task["id"]).json()
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    with factory() as db:
        assert list(db.scalars(select(RevisionPractice.interview_id))) == [other["interview_id"]]
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_link_failure_rolls_back_new_interview_runtime_and_ownership(users):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a)
    def fail(*args):
        raise RuntimeError("synthetic link failure")
    event.listen(RevisionPractice, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic link failure"):
            start(client, a, task["id"])
    finally:
        event.remove(RevisionPractice, "before_insert", fail)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 1
        assert db.scalar(select(func.count()).select_from(InterviewRuntime)) == 1
        assert db.scalar(select(func.count()).select_from(ResourceOwner)) == 1
        assert db.scalar(select(func.count()).select_from(RevisionPractice)) == 0
