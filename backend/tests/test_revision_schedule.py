from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models.entities import AccountSession, RevisionSchedule, QuestionScore, Base
from app.services.accounts import now_utc, token_hash
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source, add


def scheduled(client, factory, user, index=1, day="2026-10-24", **source_args):
    sid = source(factory, user, index, **source_args)
    task = add(client, user, sid).json()["items"][0]
    response = client.patch("/api/account/revision-tasks/" + task["id"], headers=auth(user), json={"due_date": day})
    assert response.status_code == 200, response.text
    return sid, response.json()


def test_date_only_update_reschedule_clear_and_readd_preserve_manual_state_and_scores(users):
    client, factory, a, _ = users
    sid, task = scheduled(client, factory, a)
    path = "/api/account/revision-tasks/" + task["id"]
    done = client.patch(path, headers=auth(a), json={"status": "done"}).json()
    assert done["due_date"] == "2026-10-24" and done["completed_at"]
    moved = client.patch(path, headers=auth(a), json={"due_date": "2026-10-25"}).json()
    assert moved["status"] == "done" and moved["completed_at"] == done["completed_at"]
    assert add(client, a, sid).json()["items"] == [moved]
    assert client.patch(path, headers=auth(a), json={"due_date": "2026-10-25"}).json() == moved
    restored = client.patch(path, headers=auth(a), json={"status": "todo"}).json()
    assert restored["due_date"] == "2026-10-25" and restored["completed_at"] is None
    cleared = client.patch(path, headers=auth(a), json={"due_date": None}).json()
    assert cleared["due_date"] is None and cleared["status"] == "todo"
    assert client.patch(path, headers=auth(a), json={"due_date": None}).json() == cleared
    with factory() as db:
        assert db.get(RevisionSchedule, task["id"]) is None
        assert db.scalar(select(QuestionScore.score).where(QuestionScore.interview_id == sid)) == 3


def test_status_and_date_can_be_changed_atomically(users):
    client, factory, a, _ = users
    _, task = scheduled(client, factory, a)
    response = client.patch("/api/account/revision-tasks/" + task["id"], headers=auth(a),
                            json={"due_date": "2024-02-29", "status": "done"})
    assert response.status_code == 200
    assert response.json()["due_date"] == "2024-02-29" and response.json()["completed_at"]


@pytest.mark.parametrize("day", ["2026-02-29", "2026-02-30", "2026-1-2", "20261024", "2026-W43-6",
    "2026-10-24T00:00:00Z", "1999-12-31", "2101-01-01", "", 1792800000, True, []])
def test_invalid_dates_reject_entire_update_without_changing_status(users, day):
    client, factory, a, _ = users
    _, task = scheduled(client, factory, a)
    response = client.patch("/api/account/revision-tasks/" + task["id"], headers=auth(a),
                            json={"due_date": day, "status": "done"})
    assert response.status_code == 422
    current = client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]
    assert current["status"] == "todo" and current["due_date"] == "2026-10-24"


def test_filters_counts_pagination_and_position_do_not_leak_other_account(users, monkeypatch):
    from app.services import revision
    monkeypatch.setattr(revision, "revision_today", lambda: date(2026, 10, 24))
    client, factory, a, b = users
    items = [scheduled(client, factory, a, i, day)[1] for i, day in enumerate(
        ["2026-10-23", "2026-10-20", "2026-10-24", "2026-10-25", None])]
    scheduled(client, factory, a, 10, "2026-10-24", position="python_backend", theme="Python基础")
    scheduled(client, factory, b, 20, "2026-10-23")
    client.patch("/api/account/revision-tasks/" + items[2]["id"], headers=auth(a), json={"status": "done"})
    url = "/api/account/revision-tasks?position=java_backend&status=todo"
    page = client.get(url + "&due=overdue&limit=1", headers=auth(a)).json()
    second = client.get(url + "&due=overdue&limit=1&offset=1", headers=auth(a)).json()
    assert [page["items"][0]["id"], second["items"][0]["id"]] == [items[1]["id"], items[0]["id"]]
    assert page["has_more"] and not second["has_more"] and page["total"] == 2
    assert page["counts"] == {"todo": 4, "done": 1}
    assert page["date_counts"] == {"today": 0, "overdue": 2, "upcoming": 1, "unscheduled": 1}
    assert page["today"] == "2026-10-24" and page["timezone"] == "Asia/Shanghai"
    assert len({p["id"] for p in page["positions"]}) == 2
    for key, task in [("upcoming", items[3]), ("unscheduled", items[4])]:
        data = client.get(url + "&due=" + key, headers=auth(a)).json()
        assert [r["id"] for r in data["items"]] == [task["id"]]
    done = client.get("/api/account/revision-tasks?status=done&due=today", headers=auth(a)).json()
    assert done["total"] == 1 and done["date_counts"]["today"] == 1
    empty = client.get(url + "&due=today", headers=auth(a)).json()
    assert empty["items"] == [] and empty["total"] == 0
    assert client.get(url + "&due=unknown", headers=auth(a)).status_code == 422


def test_scheduled_dates_use_beijing_midnight_not_host_timezone(users, monkeypatch):
    from app.services import revision
    client, factory, a, _ = users
    scheduled(client, factory, a, day="2026-10-24")
    for instant, expected_day, expected_count in [
        (datetime(2026, 10, 23, 15, 59, 59), "2026-10-23", 0),
        (datetime(2026, 10, 23, 16), "2026-10-24", 1),
        (datetime(2026, 10, 24, 16), "2026-10-25", 0),
    ]:
        monkeypatch.setattr(revision, "now_utc", lambda instant=instant: instant)
        result = client.get("/api/account/revision-tasks?due=today", headers=auth(a)).json()
        assert result["today"] == expected_day and result["total"] == expected_count


def test_schedule_authorization_unknown_expired_and_rejected_payloads(users):
    client, factory, a, b = users
    _, task = scheduled(client, factory, a)
    path = "/api/account/revision-tasks/" + task["id"]
    assert client.patch(path, json={"due_date": None}).status_code == 401
    assert client.patch(path, headers=auth(b), json={"due_date": None}).status_code == 404
    assert client.patch("/api/account/revision-tasks/missing", headers=auth(a), json={"due_date": None}).status_code == 404
    for payload in ({}, {"status": None}, {"due_date": None, "timezone": "UTC"}):
        assert client.patch(path, headers=auth(a), json=payload).status_code == 422
    with factory() as db:
        db.get(AccountSession, token_hash(a["access_token"])).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.patch(path, headers=auth(a), json={"due_date": None}).status_code == 401
    assert client.get("/api/account/revision-tasks?due=today", headers=auth(a)).status_code == 401


def test_source_and_account_deletion_clean_schedule_with_foreign_keys(users):
    client, factory, a, b = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
    sid, first = scheduled(client, factory, a, 1)
    _, second = scheduled(client, factory, a, 2)
    _, other = scheduled(client, factory, b, 3)
    assert client.delete("/api/account/interviews/" + sid, headers=auth(a)).status_code == 200
    with factory() as db:
        assert db.get(RevisionSchedule, first["id"]) is None
        assert db.get(RevisionSchedule, second["id"]) is not None
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    with factory() as db:
        assert list(db.scalars(select(RevisionSchedule.task_id))) == [other["id"]]
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_existing_task_survives_additive_table_upgrade(users):
    client, factory, a, _ = users
    sid = source(factory, a)
    task = add(client, a, sid).json()["items"][0]
    with factory() as db:
        engine = db.get_bind()
    RevisionSchedule.__table__.drop(engine)
    Base.metadata.create_all(engine)
    after = client.get("/api/account/revision-tasks?due=unscheduled", headers=auth(a)).json()
    assert after["items"] == [task] and after["items"][0]["due_date"] is None


def test_starting_and_deleting_independent_practice_preserves_schedule(users):
    client, factory, a, _ = users
    _, task = scheduled(client, factory, a)
    path = "/api/account/revision-tasks/" + task["id"]
    child = client.post(path + "/practice", headers=auth(a))
    assert child.status_code == 200
    assert client.delete("/api/account/interviews/" + child.json()["interview_id"], headers=auth(a)).status_code == 200
    current = client.get("/api/account/revision-tasks", headers=auth(a)).json()["items"][0]
    assert current["due_date"] == "2026-10-24" and current["status"] == "todo"
