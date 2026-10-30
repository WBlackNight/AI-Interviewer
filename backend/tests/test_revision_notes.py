from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.models.entities import AccountSession, Base, InterviewRuntime, QuestionScore, RevisionNote
from app.services.accounts import now_utc, token_hash
from tests.test_accounts import users, auth, resource, PASSWORD
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source, add


def task_for(client, factory, user, index=1):
    sid = source(factory, user, index)
    return sid, add(client, user, sid).json()["items"][0]


def url(task):
    return "/api/account/revision-tasks/" + task["id"] + "/note"


def save(client, user, task, content, version=0):
    return client.put(url(task), headers=auth(user), json={"content": content, "expected_version": version})


def test_empty_default_plain_text_newlines_unicode_limit_and_no_cache(users):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a)
    assert task["note"] == {"content": "", "version": 0, "updated_at": None}
    content = '<script>alert("local-synthetic")</script>\r\n  保留缩进\r下一行'
    response = save(client, a, task, content)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    note = response.json()
    assert note["content"] == content.replace("\r\n", "\n").replace("\r", "\n")
    assert note["version"] == 1 and note["updated_at"].endswith("Z")
    assert client.get(url(task), headers=auth(a)).json() == note
    maximum = save(client, a, task, "🧪" * 2000, 1)
    assert maximum.status_code == 200 and len(maximum.json()["content"]) == 2000
    assert save(client, a, task, "🧪" * 2001, 2).status_code == 422


def test_stale_edit_does_not_overwrite_and_clear_preserves_version(users):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a)
    first = save(client, a, task, "第一个页面的理解").json()
    assert save(client, a, task, "另一个页面的旧草稿", 0).status_code == 409
    assert client.get(url(task), headers=auth(a)).json() == first
    same = save(client, a, task, first["content"], 1).json()
    assert same == first
    cleared = save(client, a, task, "", 1).json()
    assert cleared["version"] == 2 and cleared["content"] == "" and cleared["updated_at"]
    assert save(client, a, task, "迟到的编辑", 1).status_code == 409
    assert save(client, a, task, "合并后的理解", 2).json()["version"] == 3
    with factory() as db:
        assert db.get(RevisionNote, task["id"]).version == 3


def test_note_updates_are_independent_from_state_dates_scores_and_duplicate_add(users):
    client, factory, a, _ = users
    sid, task = task_for(client, factory, a)
    path = "/api/account/revision-tasks/" + task["id"]
    done = client.patch(path, headers=auth(a), json={"status": "done", "due_date": "2026-10-25"}).json()
    note = save(client, a, task, "解释清楚B+树的磁盘访问成本").json()
    current = client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]
    assert current["note"] == note
    for key in ("status", "completed_at", "due_date", "source_score", "focus_points"):
        assert current[key] == done[key]
    assert add(client, a, sid).json()["items"][0]["note"] == note
    updated = client.patch(path, headers=auth(a), json={"status": "todo"}).json()
    assert updated["note"] == note
    with factory() as db:
        assert db.scalar(select(QuestionScore.score).where(QuestionScore.interview_id == sid)) == 3


def test_other_account_unknown_expired_and_logged_out_are_rejected(users):
    client, factory, a, b = users
    _, task = task_for(client, factory, a)
    save(client, a, task, "仅属于A的笔记")
    assert client.get(url(task)).status_code == 401
    assert client.put(url(task), json={"content": "", "expected_version": 1}).status_code == 401
    assert client.get(url(task), headers=auth(b)).status_code == 404
    assert save(client, b, task, "", 1).status_code == 404
    assert client.get("/api/account/revision-tasks", headers=auth(b)).json()["items"] == []
    assert client.get(url({"id": "missing"}), headers=auth(a)).status_code == 404
    assert save(client, a, {"id": "missing"}, "x").status_code == 404
    with factory() as db:
        db.get(AccountSession, token_hash(a["access_token"])).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.get(url(task), headers=auth(a)).status_code == 401
    assert save(client, a, task, "x", 1).status_code == 401


@pytest.mark.parametrize("payload", [
    {}, {"content": None, "expected_version": 0}, {"content": 12, "expected_version": 0},
    {"content": [], "expected_version": 0}, {"content": "x", "expected_version": True},
    {"content": "x", "expected_version": -1}, {"content": "x", "expected_version": "0"},
    {"content": "x" * 2001, "expected_version": 0},
    {"content": "x", "expected_version": 0, "status": "done"},
])
def test_invalid_payload_is_rejected_without_creating_note(users, payload):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a)
    response = client.put(url(task), headers=auth(a), json=payload)
    assert response.status_code == 422 and "x" * 2001 not in response.text
    assert client.get(url(task), headers=auth(a)).json()["version"] == 0


def test_note_is_not_copied_to_new_practice_report_or_runtime(users):
    client, factory, a, _ = users
    sid, task = task_for(client, factory, a)
    private = "PRIVATE_NOTE_NOT_A_MODEL_INSTRUCTION_391"
    save(client, a, task, private)
    child = client.post("/api/account/revision-tasks/" + task["id"] + "/practice", headers=auth(a)).json()
    assert private not in client.get("/api/interview/" + sid + "/report", headers=resource(a)).text
    assert private not in client.get("/api/interview/" + child["interview_id"] + "/report", headers=resource(a)).text
    with factory() as db:
        runtime = db.get(InterviewRuntime, child["interview_id"])
        assert private not in str(runtime.__dict__)
    assert client.delete("/api/account/interviews/" + child["interview_id"], headers=auth(a)).status_code == 200
    assert client.get(url(task), headers=auth(a)).json()["content"] == private


def test_source_account_delete_clear_notes_with_foreign_keys(users):
    client, factory, a, b = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
    sid, first = task_for(client, factory, a, 1)
    _, second = task_for(client, factory, a, 2)
    _, other = task_for(client, factory, b, 3)
    for user, task in ((a, first), (a, second), (b, other)):
        save(client, user, task, "复习记录")
    assert client.delete("/api/account/interviews/" + sid, headers=auth(a)).status_code == 200
    with factory() as db:
        assert db.get(RevisionNote, first["id"]) is None
        assert db.get(RevisionNote, second["id"]) is not None
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    with factory() as db:
        assert list(db.scalars(select(RevisionNote.task_id))) == [other["id"]]
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_additive_note_table_upgrade_preserves_existing_task(users):
    client, factory, a, _ = users
    _, task = task_for(client, factory, a)
    with factory() as db:
        engine = db.get_bind()
    RevisionNote.__table__.drop(engine)
    Base.metadata.create_all(engine)
    assert client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0] == task
