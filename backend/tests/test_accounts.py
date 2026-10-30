from datetime import timedelta

import pytest
from sqlalchemy import select, func
from starlette.websockets import WebSocketDisconnect

from app.models.entities import (Account, AccountSession, AccessGrant, ResourceOwner,
    Interview, InterviewRuntime, InterviewEvent, InterviewSubmission, QuestionScore,
    TurnMetadata, Resume, User)
from app.services.accounts import AuthThrottle, now_utc, token_hash
from tests.test_ws_recovery import api, create, connect, answer, receive_turn
from tests.auth_helpers import register as register_account

PASSWORD = "synthetic-passphrase-123"


@pytest.fixture
def users(api, monkeypatch):
    from app.api import accounts
    monkeypatch.setattr(accounts, "throttle", AuthThrottle())
    client, factory = api
    def register(username):
        result = register_account(client, json={"username": username, "password": PASSWORD})
        assert result.status_code == 200, result.text
        return result.json()
    a, b = register("user_a"), register("user_b")
    return client, factory, a, b


def auth(user):
    return {"Authorization": "Bearer " + user["access_token"]}


def resource(user):
    return {"X-Interview-Token": user["access_token"]}


def owned(client, user):
    response = client.post("/api/interview", headers=auth(user),
        json={"position": "python_backend", "themes": ["Python基础"]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["account_owned"] and data["access_token"] is None
    return data


def test_registration_hashes_password_and_session_and_normalizes_login(users):
    client, factory, a, _ = users
    login = client.post("/api/auth/login", json={"username": " USER_A ", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["access_token"] != a["access_token"]
    assert client.get("/api/auth/me", headers=auth(a)).json() == a["account"]
    with factory() as db:
        account = db.get(Account, a["account"]["id"])
        assert PASSWORD not in account.password_hash and account.password_hash.startswith("pbkdf2_sha256$600000$")
        assert db.get(AccountSession, a["access_token"]) is None
        assert db.get(AccountSession, token_hash(a["access_token"])) is not None
    assert PASSWORD not in login.text and "password_hash" not in login.text
    assert register_account(client, json={"username": "USER_A", "password": PASSWORD}).status_code == 409


@pytest.mark.parametrize("username,password", [("x", PASSWORD), ("bad name", PASSWORD),
    ("中文用户名", PASSWORD), ("user_x", "secret"), ("user_x", "x" * 129)])
def test_invalid_credentials_never_echo_input(api, username, password):
    client, _ = api
    response = register_account(client, json={"username": username, "password": password})
    assert response.status_code == 422
    assert password not in response.text


def test_bad_password_unknown_user_and_expired_session(users):
    client, factory, a, _ = users
    for username in ("user_a", "missing_user"):
        response = client.post("/api/auth/login", json={"username": username, "password": "wrong-password-123"})
        assert response.status_code == 401 and response.json()["detail"] == "用户名或密码错误"
    with factory() as db:
        db.get(AccountSession, token_hash(a["access_token"])).expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me", headers=auth(a)).status_code == 401
    assert client.get("/api/account/interviews", headers=auth(a)).status_code == 401
    assert client.post("/api/interview", json={}, headers=auth(a)).status_code == 401


def test_claim_revokes_anonymous_grant_and_blocks_other_accounts(users):
    client, factory, a, b = users
    anonymous = create(client)
    path = f'/api/account/interviews/{anonymous["interview_id"]}/claim'
    assert client.post(path, json={"access_token": anonymous["access_token"]}).status_code == 401
    assert client.post(path, headers=auth(a), json={"access_token": "0" * 64}).status_code == 403
    assert client.post(path, headers=auth(a), json={"access_token": anonymous["access_token"]}).status_code == 200
    assert client.post(path, headers=auth(a), json={"access_token": "0" * 64}).status_code == 200
    assert client.post(path, headers=auth(b), json={"access_token": anonymous["access_token"]}).status_code == 403
    base = f'/api/interview/{anonymous["interview_id"]}'
    assert client.get(base + "/report", headers=resource(a)).status_code == 200
    assert client.get(base + "/report", headers=resource(anonymous)).status_code == 403
    with factory() as db:
        assert db.get(AccessGrant, ("interview", anonymous["interview_id"])) is None
        assert db.get(ResourceOwner, ("interview", anonymous["interview_id"])).account_id == a["account"]["id"]


@pytest.mark.parametrize("suffix", ["", "/report", "/report/export?format=json", "/usage"])
def test_owned_resource_reads_require_matching_account(users, suffix):
    client, _, a, b = users
    item = owned(client, a)
    path = f'/api/interview/{item["interview_id"]}' + suffix
    assert client.get(path).status_code == 403
    assert client.get(path, headers=resource(b)).status_code == 403
    assert client.get(path, headers=resource(a)).status_code == 200


def test_live_websocket_loses_access_after_claim_or_logout(users):
    client, _, a, _ = users
    anonymous = create(client)
    with connect(client, anonymous) as (socket, snapshot):
        assert client.post(f'/api/account/interviews/{anonymous["interview_id"]}/claim',
            headers=auth(a), json={"access_token": anonymous["access_token"]}).status_code == 200
        socket.send_json(answer(snapshot))
        assert socket.receive_json()["code"] == "access_revoked"
    signed = {**anonymous, "access_token": a["access_token"]}
    with connect(client, signed) as (socket, snapshot):
        assert client.post("/api/auth/logout", headers=auth(a)).status_code == 200
        socket.send_json(answer(snapshot))
        assert socket.receive_json()["code"] == "access_revoked"
    with pytest.raises(WebSocketDisconnect):
        with connect(client, signed):
            pass


def test_login_again_recovers_paginated_history_and_logout_is_session_scoped(users):
    client, _, a, b = users
    ids = {owned(client, a)["interview_id"] for _ in range(3)}
    owned(client, b)
    other = client.post("/api/auth/login", json={"username": "user_a", "password": PASSWORD}).json()
    first = client.get("/api/account/interviews?limit=2", headers=auth(other)).json()
    second = client.get("/api/account/interviews?limit=2&offset=2", headers=auth(other)).json()
    assert first["total"] == 3 and first["has_more"] and not second["has_more"]
    assert {r["interview_id"] for r in first["items"] + second["items"]} == ids
    assert client.get("/api/account/interviews?limit=51", headers=auth(a)).status_code == 422
    assert client.post("/api/auth/logout", headers=auth(a)).status_code == 200
    assert client.get("/api/auth/me", headers=auth(a)).status_code == 401
    assert client.get("/api/auth/me", headers=auth(other)).status_code == 200


def test_signed_resume_creation_and_interview_preserve_ownership(users):
    client, factory, a, b = users
    resume = client.post("/api/resume", json={"resume_text": "专业技能\nPython、SQL"}, headers=auth(a)).json()
    assert resume["account_owned"] and resume["access_token"] is None
    payload = {"resume_id": resume["resume_id"], "position": "python_backend"}
    assert client.post("/api/interview", json=payload,
        headers={"X-Resume-Token": b["access_token"]}).status_code == 403
    created = client.post("/api/interview", json=payload,
        headers={"X-Resume-Token": a["access_token"]}).json()
    assert created["account_owned"] and created["access_token"] is None
    with factory() as db:
        assert db.get(ResourceOwner, ("resume", resume["resume_id"])).account_id == a["account"]["id"]


def test_owned_practice_retry_inherits_account_without_copying_answers(users):
    from tests.test_practice import finish_practice
    client, factory, a, b = users
    item = owned(client, a)
    signed = {**item, "access_token": a["access_token"]}
    finish_practice(client, signed, ["Python基础"])
    path = f'/api/interview/{item["interview_id"]}/practice'
    assert client.post(path, headers=resource(b)).status_code == 403
    retry = client.post(path, headers=resource(a)).json()
    assert retry["account_owned"] and retry["access_token"] is None
    with factory() as db:
        assert db.get(ResourceOwner, ("interview", retry["interview_id"])).account_id == a["account"]["id"]
        assert db.scalar(select(func.count()).select_from(QuestionScore).where(
            QuestionScore.interview_id == retry["interview_id"])) == 0


def test_delete_record_checks_owner_running_state_and_removes_children(users):
    from tests.test_practice import finish_practice
    client, factory, a, b = users
    item = owned(client, a)
    path = f'/api/account/interviews/{item["interview_id"]}'
    assert client.delete(path, headers=auth(b)).status_code == 403
    signed = {**item, "access_token": a["access_token"]}
    with connect(client, signed):
        pass
    assert client.delete(path, headers=auth(a)).status_code == 409
    finish_practice(client, signed, ["Python基础"])
    assert client.delete(path, headers=auth(a)).status_code == 200
    with factory() as db:
        for model in (Interview, InterviewEvent, QuestionScore, InterviewRuntime, InterviewSubmission, TurnMetadata):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    assert client.get(f'/api/interview/{item["interview_id"]}/report', headers=resource(a)).status_code == 403


def test_account_delete_requires_password_and_preserves_unrelated_resources(users):
    client, factory, a, b = users
    mine, other = owned(client, a), owned(client, b)
    client.post("/api/resume", json={"resume_text": "专业技能\nPython"}, headers=auth(a))
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": "wrong-password-123"}).status_code == 401
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me", headers=auth(a)).status_code == 401
    with factory() as db:
        assert db.get(Account, a["account"]["id"]) is None
        assert db.get(Interview, mine["interview_id"]) is None
        assert db.get(Interview, other["interview_id"]) is not None
        assert db.scalar(select(func.count()).select_from(Resume)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_auth_admission_rejects_flood_and_busy_hash_workers(api, monkeypatch):
    from app.api import accounts
    client, _ = api
    limiter = AuthThrottle()
    monkeypatch.setattr(accounts, "throttle", limiter)
    monkeypatch.setattr(accounts, "verify_password", lambda *a: False)
    payload = {"username": "missing_user", "password": PASSWORD}
    for _ in range(20):
        assert client.post("/api/auth/login", json=payload).status_code == 401
    assert client.post("/api/auth/login", json=payload).status_code == 429
    limiter = AuthThrottle()
    monkeypatch.setattr(accounts, "throttle", limiter)
    limiter.work.acquire(); limiter.work.acquire()
    try:
        assert client.post("/api/auth/login", json=payload).status_code == 429
    finally:
        limiter.work.release(); limiter.work.release()


def test_logout_during_scoring_discards_results_before_commit(users, monkeypatch):
    from app.api import ws
    from sqlalchemy import delete
    client, factory, a, _ = users
    item = owned(client, a)
    original = ws.build_scorer
    def build(*args):
        scorer = original(*args)
        score = scorer.score
        def revoked_score(*args):
            result = score(*args)
            with factory() as db:
                db.execute(delete(AccountSession).where(AccountSession.token_hash == token_hash(a["access_token"])))
                db.commit()
            return result
        scorer.score = revoked_score
        return scorer
    monkeypatch.setattr(ws, "build_scorer", build)
    with connect(client, {**item, "access_token": a["access_token"]}) as (socket, snapshot):
        socket.send_json(answer(snapshot))
        assert socket.receive_json()["code"] == "access_revoked"
    with factory() as db:
        assert db.get(InterviewRuntime, item["interview_id"]).version == 1
        assert db.scalar(select(func.count()).select_from(QuestionScore)) == 0
        assert db.scalar(select(func.count()).select_from(InterviewSubmission)) == 0


def test_deletion_is_atomic_for_running_account_and_respects_foreign_keys(users):
    from sqlalchemy import text
    client, factory, a, _ = users
    with factory() as db:
        db.execute(text("PRAGMA foreign_keys=ON")); db.commit()
    resume = client.post("/api/resume", headers=auth(a), json={"resume_text": "专业技能\nPython"}).json()
    created = client.post("/api/interview", json={"resume_id": resume["resume_id"], "position": "python_backend"},
        headers={**auth(a), "X-Resume-Token": a["access_token"]}).json()
    with connect(client, {**created, "access_token": a["access_token"]}):
        pass
    response = client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD})
    assert response.status_code == 409
    with factory() as db:
        assert db.get(Account, a["account"]["id"]) is not None
        assert db.get(Resume, resume["resume_id"]) is not None
        db.get(Interview, created["interview_id"]).status = "finished"
        db.commit()
    assert client.request("DELETE", "/api/account", headers=auth(a), json={"password": PASSWORD}).status_code == 200
    with factory() as db:
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_resume_token_cannot_override_a_different_signed_identity(users):
    client, _, a, b = users
    resume = client.post("/api/resume", headers=auth(b), json={"resume_text": "专业技能\nPython"}).json()
    response = client.post("/api/interview", json={"position": "python_backend", "resume_id": resume["resume_id"]},
        headers={**auth(a), "X-Resume-Token": b["access_token"]})
    assert response.status_code == 403
