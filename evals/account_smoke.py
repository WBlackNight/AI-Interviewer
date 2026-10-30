"""离线账户真实服务冒烟：认领、重新登录找回、WS恢复、复练与删除。

python evals/account_smoke.py --json-out docs/logs/account-local.json
只启动隔离数据库，不使用真实用户或外部模型，不输出密码/令牌。
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.request
import uuid

from smoke_e2e import BACKEND, OPENER, Server, request
from practice_smoke import complete, denied


def delete(base, path, headers, payload=None):
    req = urllib.request.Request(base + path, method="DELETE",
        headers={"Content-Type": "application/json", **headers},
        data=json.dumps(payload).encode() if payload is not None else None)
    with OPENER.open(req, timeout=20) as response:
        assert response.headers["Cache-Control"] == "no-store"
        return json.loads(response.read())


async def run(server):
    base = server.base
    password = "synthetic-account-password-" + uuid.uuid4().hex
    users = [request(base, "/api/auth/register", {"username": name, "password": password})
             for name in ("smoke_owner", "smoke_other")]
    a, b = users
    auth = lambda user: {"Authorization": "Bearer " + user["access_token"]}
    resource = lambda user: {"X-Interview-Token": user["access_token"]}
    anonymous = request(base, "/api/interview", {"position": "java_backend", "themes": ["MySQL"]})
    source_id = anonymous["interview_id"]
    request(base, f"/api/account/interviews/{source_id}/claim", {"access_token": anonymous["access_token"]}, auth(a))
    denied(base, f"/api/interview/{source_id}/report", headers=resource(anonymous))
    denied(base, f"/api/interview/{source_id}/report", headers=resource(b))
    report, source_result, _ = await complete(server, {**anonymous, "access_token": a["access_token"]}, ["MySQL"], restart=True)
    # 新会话相当于另一标签页/设备；凭据来自重新登录，历史来自服务端。
    second = request(base, "/api/auth/login", {"username": "smoke_owner", "password": password})
    assert second["access_token"] != a["access_token"]
    page = request(base, "/api/account/interviews?limit=1", headers=auth(second))
    assert page["total"] == 1 and page["items"][0]["interview_id"] == source_id
    recovered_report = request(base, f"/api/interview/{source_id}/report", headers=resource(second))
    assert recovered_report == report
    assert report["scoring_sources"] == {"heuristic": report["answer_count"]}
    assert all(row["scoring_origin"]["source"] == "heuristic" and
        len(row["scoring_origin"]["main_question_version"]) == 64 for row in report["per_question"])
    retry = request(base, f"/api/interview/{source_id}/practice", {}, resource(second))
    assert retry["account_owned"] and retry["access_token"] is None
    _, retry_result, _ = await complete(server, {**retry, "access_token": second["access_token"]}, ["MySQL"], restart=True)
    review = request(base, "/api/account/review?position=java_backend&theme=MySQL&limit=1", headers=auth(second))
    assert review["total"] == 2 and review["has_more"] and review["session_count"] == 1
    row = review["items"][0]
    assert row["interview_id"] == retry["interview_id"] and row["repeat_question_count"] == 2
    assert row["scoring_sources"] == {"heuristic": 8} and row["unknown_question_version_count"] == 0
    assert request(base, "/api/account/review", headers=auth(b))["total"] == 0
    request(base, "/api/auth/logout", {}, auth(a))
    denied(base, f"/api/interview/{source_id}/report", headers=resource(a))
    assert request(base, "/api/auth/me", headers=auth(second))["username"] == "smoke_owner"
    resume = request(base, "/api/resume", {"resume_text": "专业技能\nPython、SQL"}, auth(second))
    assert resume["account_owned"] and resume["access_token"] is None
    created = request(base, "/api/interview", {"position": "python_backend", "resume_id": resume["resume_id"]},
        {**auth(second), "X-Resume-Token": second["access_token"]})
    assert created["account_owned"] and created["access_token"] is None
    assert delete(base, f"/api/account/interviews/{source_id}", auth(second))["deleted"]
    assert request(base, "/api/account/review", headers=auth(second))["total"] == 1
    denied(base, f"/api/interview/{source_id}/report", headers=resource(second))
    assert delete(base, "/api/account", auth(second), {"password": password})["deleted"]
    denied(base, "/api/auth/me", headers=auth(second), status=401)
    denied(base, "/api/auth/login", payload={"username": "smoke_owner", "password": password}, status=401)
    assert request(base, "/api/auth/me", headers=auth(b))["username"] == "smoke_other"
    assert not request(base, "/api/health")["llm_enabled"]
    return {"result": "passed", "external_model_calls": 0, "synthetic_inputs_only": True,
        "anonymous_claim_and_revocation": True, "cross_account_denied": True,
        "relogin_history_recovery": True, "session_scoped_logout": True,
        "owned_resume_and_interview": True, "record_and_account_deletion": True,
        "scoring_origin_persisted": True, "review_pagination_and_repeat_questions": True,
        "review_cross_account_isolation": True,
        "source": source_result, "owned_retry": retry_result,
        "browser_multi_device_ui_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-account-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "account.sqlite3")
        try:
            server.start()
            result = asyncio.run(run(server))
        finally:
            server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
