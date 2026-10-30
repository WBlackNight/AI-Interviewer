"""离线复习任务冒烟：报告加入、进度、重启、独立登录、隔离及删除。

python evals/revision_smoke.py --json-out docs/logs/revision-local.json
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.error
import urllib.request
import uuid

from smoke_e2e import BACKEND, OPENER, Server, request
from practice_smoke import complete, denied
from account_smoke import delete


def patch(base, path, headers, status, expected=200):
    return update(base, path, headers, {"status": status}, expected)


def update(base, path, headers, payload, expected=200):
    req = urllib.request.Request(base + path, method="PATCH",
        headers={"Content-Type": "application/json", **headers}, data=json.dumps(payload).encode())
    try:
        response = OPENER.open(req, timeout=20)
    except urllib.error.HTTPError as error:
        assert error.code == expected, error.code
        return None
    with response:
        assert response.status == expected and response.headers["Cache-Control"] == "no-store"
        return json.loads(response.read())


async def run(server):
    base = server.base
    password = "synthetic-revision-" + uuid.uuid4().hex
    a, b = [request(base, "/api/auth/register", {"username": name, "password": password})
            for name in ("revision_owner", "revision_other")]
    auth = lambda user: {"Authorization": "Bearer " + user["access_token"]}
    source = request(base, "/api/interview", {"position": "java_backend", "themes": ["MySQL"]}, auth(a))
    sid = source["interview_id"]
    path = f"/api/account/interviews/{sid}/revision-tasks"
    denied(base, path, payload={}, headers=auth(a), status=409)
    report, _, _ = await complete(server, {**source, "access_token": a["access_token"]}, ["MySQL"])
    denied(base, path, payload={}, status=401)
    denied(base, path, payload={}, headers=auth(b))
    added = request(base, path, {}, auth(a))
    assert added["added"] == 1 and added["existing"] == 0
    task = added["items"][0]
    assert task["theme"] == "MySQL" and task["status"] == "todo" and task["focus_points"]
    second = request(base, "/api/auth/login", {"username": "revision_owner", "password": password})
    task_path = "/api/account/revision-tasks/" + task["id"]
    done = patch(base, task_path, auth(second), "done")
    assert done["completed_at"]
    patch(base, task_path, auth(b), "done", expected=404)
    await asyncio.to_thread(server.restart)
    recovered = request(base, "/api/account/revision-tasks?status=done", headers=auth(second))
    assert recovered["items"] == [done] and recovered["counts"] == {"todo": 0, "done": 1}
    again = request(base, path, {}, auth(second))
    assert again["added"] == 0 and again["items"] == [done]
    assert request(base, f"/api/interview/{sid}/report", headers={"X-Interview-Token": second["access_token"]}) == report
    assert request(base, "/api/account/revision-tasks", headers=auth(b))["total"] == 0
    assert patch(base, task_path, auth(second), "todo")["completed_at"] is None
    python = request(base, "/api/interview", {"position": "python_backend", "themes": ["Python基础"]}, auth(second))
    await complete(server, {**python, "access_token": second["access_token"]}, ["Python基础"])
    request(base, f'/api/account/interviews/{python["interview_id"]}/revision-tasks', {}, auth(second))
    page = request(base, "/api/account/revision-tasks?position=python_backend&limit=1", headers=auth(second))
    assert page["total"] == 1 and page["items"][0]["theme"] == "Python基础"
    assert len(page["positions"]) == 2
    assert delete(base, f"/api/account/interviews/{sid}", auth(second))["deleted"]
    assert request(base, "/api/account/revision-tasks", headers=auth(second))["total"] == 1
    patch(base, task_path, auth(second), "done", expected=404)
    assert delete(base, "/api/account", auth(second), {"password": password})["deleted"]
    assert request(base, "/api/auth/me", headers=auth(b))["username"] == "revision_other"
    return {"result": "passed", "synthetic_inputs_only": True, "external_model_calls": 0,
            "completed_reports": 2, "restart_verified": 1, "independent_login": True,
            "manual_progress_persisted": True, "duplicate_preserves_completed": True,
            "scores_unchanged": True, "cross_account_isolation": True,
            "position_filter": True, "undo_verified": True,
            "source_and_account_deletion_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-revision-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "revision.sqlite3")
        try:
            server.start(); result = asyncio.run(run(server))
        finally:
            server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
