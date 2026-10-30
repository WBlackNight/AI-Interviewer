from datetime import timedelta
from dataclasses import replace

import pytest
from sqlalchemy import func, select, text

from app.models.entities import AccountSession, QuestionScore, RevisionTask
from app.services.accounts import now_utc, token_hash
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api, create
from tests.test_score_origin_review import add_session, record


def source(factory, user, index=1, value=3, status="finished", theme="MySQL", position="java_backend"):
    row = record(value=value, theme=theme)
    row = replace(row, result=replace(row.result, key_points_missed=("范围查询", "磁盘IO", "范围查询")))
    return add_session(factory, user["account"]["id"], index, [row], position=position, status=status)


def add(client, user, interview_id):
    return client.post(f"/api/account/interviews/{interview_id}/revision-tasks", headers=auth(user))


def test_tasks_derive_from_report_and_do_not_copy_private_text_or_accept_client_scores(users):
    client, factory, a, b = users
    sid = source(factory, a)
    response = client.post(f"/api/account/interviews/{sid}/revision-tasks", headers=auth(a),
                           json={"source_score": 10, "theme": "forged", "status": "done"})
    assert response.status_code == 200, response.text
    result = response.json()
    task = result["items"][0]
    assert result["added"] == 1 and result["existing"] == 0
    assert task["theme"] == "MySQL" and task["source_score"] == 3 and task["status"] == "todo"
    assert task["focus_points"] == ["范围查询", "磁盘IO"]
    assert task["completed_at"] is None and task["created_at"].endswith("Z")
    assert "private answer" not in response.text and "private question" not in response.text
    assert "account_id" not in task
    with factory() as db:
        saved = db.get(RevisionTask, task["id"])
        assert saved.account_id == a["account"]["id"]
    assert client.get("/api/account/revision-tasks", headers=auth(b)).json()["total"] == 0


def test_task_threshold_uses_main_question_aggregation_and_caps_at_report_weak_topics(users):
    client, factory, a, _ = users
    rows = [record("a", 0), record("a#p1", 10), record("b", 10),
            record("c", 1, theme="Redis"), record("d", 2, theme="JVM"), record("e", 3, theme="Spring")]
    sid = add_session(factory, a["account"]["id"], 1, rows)
    tasks = add(client, a, sid).json()["items"]
    # MySQL主问题等权：(5+10)/2=7.5；其余只保留报告最弱的2主题。
    assert [r["theme"] for r in tasks] == ["Redis", "JVM"]


def test_done_undo_and_readd_are_idempotent_and_never_modify_scores(users):
    client, factory, a, _ = users
    sid = source(factory, a)
    task = add(client, a, sid).json()["items"][0]
    path = "/api/account/revision-tasks/" + task["id"]
    first = client.patch(path, json={"status": "done"}, headers=auth(a)).json()
    assert first["completed_at"] and first["status"] == "done"
    assert client.patch(path, json={"status": "done"}, headers=auth(a)).json() == first
    again = add(client, a, sid).json()
    assert again["added"] == 0 and again["existing"] == 1 and again["items"] == [first]
    undone = client.patch(path, json={"status": "todo"}, headers=auth(a)).json()
    assert undone["status"] == "todo" and undone["completed_at"] is None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RevisionTask)) == 1
        assert db.scalar(select(QuestionScore.score).where(QuestionScore.interview_id == sid)) == 3


def test_authorization_unclaimed_cross_account_unknown_task_and_expiry(users):
    client, factory, a, b = users
    sid = source(factory, a)
    path = f"/api/account/interviews/{sid}/revision-tasks"
    assert client.post(path).status_code == 401
    assert add(client, b, sid).status_code == 403
    assert add(client, a, create(client)["interview_id"]).status_code == 403
    task = add(client, a, sid).json()["items"][0]
    url = "/api/account/revision-tasks/" + task["id"]
    assert client.patch(url, json={"status": "done"}, headers=auth(b)).status_code == 404
    assert client.patch(url, json={"status": "done"}).status_code == 401
    assert client.patch("/api/account/revision-tasks/missing", json={"status": "done"}, headers=auth(a)).status_code == 404
    with factory() as db:
        db.get(AccountSession, token_hash(a["access_token"])).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/account/revision-tasks", headers=auth(a)).status_code == 401
    assert client.patch(url, json={"status": "done"}, headers=auth(a)).status_code == 401
    assert add(client, a, sid).status_code == 401


@pytest.mark.parametrize("status", ["created", "running", "cancelled"])
def test_partial_and_cancelled_interviews_cannot_generate_tasks(users, status):
    client, factory, a, _ = users
    assert add(client, a, source(factory, a, status=status)).status_code == 409
    assert client.get("/api/account/revision-tasks", headers=auth(a)).json()["total"] == 0


@pytest.mark.parametrize("records", [[], [record(value=7)]])
def test_no_scores_or_exact_pass_boundary_does_not_invent_task(users, records):
    client, factory, a, _ = users
    sid = add_session(factory, a["account"]["id"], 1, records)
    assert add(client, a, sid).status_code == 422


def test_list_paginates_stably_and_counts_match_position_not_status_filter(users):
    client, factory, a, b = users
    for index in range(23):
        add(client, a, source(factory, a, index))
    py_id = source(factory, a, 24, theme="Python基础", position="python_backend")
    py_task = add(client, a, py_id).json()["items"][0]
    client.patch("/api/account/revision-tasks/" + py_task["id"], json={"status": "done"}, headers=auth(a))
    add(client, b, source(factory, b))
    first = client.get("/api/account/revision-tasks?position=java_backend&status=todo", headers=auth(a)).json()
    last = client.get("/api/account/revision-tasks?position=java_backend&status=todo&offset=20", headers=auth(a)).json()
    assert first["total"] == 23 and len(first["items"]) == 20 and first["has_more"]
    assert len(last["items"]) == 3 and not last["has_more"]
    assert len({t["id"] for t in first["items"] + last["items"]}) == 23
    assert first["counts"] == {"todo": 23, "done": 0}
    done = client.get("/api/account/revision-tasks?status=done", headers=auth(a)).json()
    assert done["total"] == 1 and done["items"][0]["id"] == py_task["id"]
    assert done["counts"] == {"todo": 23, "done": 1}
    assert {p["id"] for p in done["positions"]} == {"java_backend", "python_backend"}
    assert client.get("/api/account/revision-tasks?position=absent", headers=auth(a)).json()["total"] == 0


def test_invalid_updates_filters_and_pagination_are_rejected(users):
    client, factory, a, _ = users
    task = add(client, a, source(factory, a)).json()["items"][0]
    for payload in ({"status": "deleted"}, {"status": "done", "source_score": 10}, {}):
        assert client.patch("/api/account/revision-tasks/" + task["id"], json=payload, headers=auth(a)).status_code == 422
    for query in ("status=bad", "limit=51", "offset=-1", "position="):
        assert client.get("/api/account/revision-tasks?" + query, headers=auth(a)).status_code == 422


def test_source_and_account_deletion_clean_tasks_with_foreign_keys_enabled(users):
    client, factory, a, b = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
    ids = [source(factory, a, index) for index in (1, 2)]
    for sid in ids:
        add(client, a, sid)
    other = add(client, b, source(factory, b)).json()["items"][0]
    assert client.delete("/api/account/interviews/" + ids[0], headers=auth(a)).status_code == 200
    assert client.get("/api/account/revision-tasks", headers=auth(a)).json()["total"] == 1
    assert client.request("DELETE", "/api/account", json={"password": PASSWORD}, headers=auth(a)).status_code == 200
    with factory() as db:
        assert list(db.scalars(select(RevisionTask.id))) == [other["id"]]
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_focus_points_are_bounded_and_empty_points_remain_empty(users):
    client, factory, a, _ = users
    row = record(value=0)
    row = replace(row, result=replace(row.result, key_points_missed=tuple([" ", "long" * 100] + [str(i) for i in range(20)])))
    sid = add_session(factory, a["account"]["id"], 1, [row])
    points = add(client, a, sid).json()["items"][0]["focus_points"]
    assert len(points) == 8 and max(map(len, points)) == 300
    sid2 = add_session(factory, a["account"]["id"], 2, [record(value=0)])
    assert add(client, a, sid2).json()["items"][0]["focus_points"] == []
