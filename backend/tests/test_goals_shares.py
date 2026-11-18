from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.entities import Interview, PreparationGoal, PreparationPractice, ReportShare
from app.services.accounts import now_utc
from tests.test_accounts import users, auth, PASSWORD
from tests.test_ws_recovery import api
from tests.test_preparation import create, listing, start, patch, offline, PATH
from tests.test_revision_tasks import source


def share(client, user, sid, **changes):
    return client.post(f"/api/account/interviews/{sid}/shares", headers=auth(user),
                       json={"hours": 24, "scope": "summary", **changes})


def read(client, created):
    token = created["share_path"].split("#")[1]
    return client.get("/api/shared-report", headers={"X-Report-Share": token})


def test_goal_progress_is_derived_scoped_and_versioned(users):
    client, factory, a, b = users
    key = create(client, a, target_sessions=3)
    assert listing(client, a)["items"][0]["target_sessions"] == 3
    practice = start(client, a, key).json()["interview_id"]
    assert listing(client, a)["items"][0]["finished_count"] == 0
    with factory() as db:
        db.get(Interview, practice).status = "finished"
        db.commit()
    assert listing(client, a)["items"][0]["finished_count"] == 1
    dashboard = client.get("/api/account/dashboard", headers=auth(a)).json()
    assert dashboard["preparation"]["items"][0]["target_sessions"] == 3
    assert dashboard["preparation"]["items"][0]["finished_count"] == 1
    exported = client.get("/api/account/revision-export", headers=auth(a)).json()
    assert exported["plans"][0]["target_sessions"] == 3
    assert patch(client, b, key, target_sessions=1).status_code == 404
    assert patch(client, a, key, target_sessions=1).json()["version"] == 1
    assert patch(client, a, key, target_sessions=2).status_code == 409
    assert patch(client, a, key, version=1, target_sessions=None).status_code == 200
    assert listing(client, a)["items"][0]["target_sessions"] is None
    assert listing(client, a)["items"][0]["finished_count"] == 1


@pytest.mark.parametrize("target", [0, 51, True, 1.5, "5"])
def test_goal_rejects_invalid_target(users, target):
    client, _, a, _ = users
    assert client.post(PATH, headers=auth(a), json={"name": "test", "position": "java_backend",
        "themes": ["MySQL"], "target_sessions": target}).status_code == 422


def test_removing_archived_plan_cleans_goal_but_keeps_practice(users):
    client, factory, a, _ = users
    key = create(client, a, target_sessions=2)
    sid = start(client, a, key).json()["interview_id"]
    assert patch(client, a, key, status="archived").status_code == 200
    assert client.delete(PATH + "/" + key + "?expected_version=1", headers=auth(a)).status_code == 200
    with factory() as db:
        assert db.get(PreparationGoal, key) is None
        assert db.get(Interview, sid) is not None


def test_share_defaults_to_safe_snapshot_and_supports_explicit_answers(users):
    client, factory, a, b = users
    sid = source(factory, a)
    assert share(client, b, sid).status_code == 404
    response = share(client, a, sid)
    assert response.status_code == 200, response.text
    created = response.json()
    public = read(client, created)
    assert public.status_code == 200
    assert public.headers["cache-control"] == "no-store"
    assert public.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in public.headers["x-robots-tag"]
    assert "private answer" not in public.text and "private question" not in public.text
    assert a["account"]["id"] not in public.text
    assert sid not in public.text and "scoring_origin" not in public.text
    detailed = share(client, a, sid, scope="answers").json()
    assert "private answer" in read(client, detailed).text
    listing_response = client.get(f"/api/account/interviews/{sid}/shares", headers=auth(a))
    assert "share_path" not in listing_response.text and created["share_path"].split("#")[1] not in listing_response.text
    with factory() as db:
        row = db.get(ReportShare, created["id"])
        assert row.token_hash != created["share_path"].split("#")[1]
        assert "access_token" not in str(row.snapshot)
    assert client.post(f'/api/account/report-shares/{created["id"]}/revoke', headers=auth(b)).status_code == 404
    assert client.post(f'/api/account/report-shares/{created["id"]}/revoke', headers=auth(a)).status_code == 200
    assert read(client, created).status_code == 404
    assert read(client, detailed).status_code == 200
    with factory() as db:
        db.get(ReportShare, detailed["id"]).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert read(client, detailed).status_code == 404


def test_shares_have_limits_and_disappear_with_source_and_account(users):
    client, factory, a, b = users
    sid = source(factory, a)
    assert share(client, a, sid, hours=2).status_code == 422
    assert share(client, a, sid, scope="all").status_code == 422
    created = [share(client, a, sid).json() for _ in range(20)]
    assert share(client, a, sid).status_code == 409
    with factory() as db:
        goal_plan = create(client, a, target_sessions=2)
        assert db.get(PreparationGoal, goal_plan)
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    assert read(client, created[0]).status_code == 404
    with factory() as db:
        assert db.scalar(select(ReportShare.id)) is None
        assert db.scalar(select(PreparationGoal.plan_id)) is None
    assert client.get("/share").status_code == 200


def test_deleting_report_invalidates_its_shares(users):
    client, factory, a, _ = users
    sid = source(factory, a)
    created = share(client, a, sid).json()
    response = client.delete(f"/api/account/interviews/{sid}", headers=auth(a))
    assert response.status_code == 200, response.text
    assert read(client, created).status_code == 404
