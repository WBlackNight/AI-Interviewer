"""隔离任务专项冒烟：双岗位、并发重试去重、来源/进度、重启与独立删除。

python evals/revision_practice_smoke.py --json-out docs/logs/revision-practice-local.json
仅合成账户/回答，离线评分；不输出凭据。
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import uuid

from smoke_e2e import BACKEND, Server, request
from practice_smoke import complete, denied
from account_smoke import delete
from revision_smoke import patch


async def run(server):
    base = server.base
    password = "synthetic-task-practice-" + uuid.uuid4().hex
    a, b = [request(base, "/api/auth/register", {"username": name, "password": password})
            for name in ("task_practice_owner", "task_practice_other")]
    auth = lambda user: {"Authorization": "Bearer " + user["access_token"]}
    headers = {"X-Interview-Token": a["access_token"]}
    cases = []
    for position, theme, manual in [("java_backend", "MySQL", "done"), ("python_backend", "Python基础", "todo")]:
        source = request(base, "/api/interview", {"position": position, "themes": [theme], "difficulty": "hard"}, auth(a))
        source_report, _, _ = await complete(server, {**source, "access_token": a["access_token"]}, [theme])
        sid = source["interview_id"]
        task = request(base, f"/api/account/interviews/{sid}/revision-tasks", {}, auth(a))["items"][0]
        task_path = f'/api/account/revision-tasks/{task["id"]}'
        before = patch(base, task_path, auth(a), manual)
        denied(base, task_path + "/practice", payload={}, status=401)
        denied(base, task_path + "/practice", payload={}, headers=auth(b), status=404)
        starts = await asyncio.gather(*[asyncio.to_thread(request, base, task_path + "/practice", {}, auth(a)) for _ in range(4)])
        assert len({r["interview_id"] for r in starts}) == 1
        assert sum(not r["reused"] for r in starts) == 1
        child = starts[0]
        assert child["account_owned"] and child["access_token"] is None
        assert [p["theme"] for p in child["plan"]] == [theme]
        assert child["plan"][0]["difficulty"] == "hard" and not child["plan"][0]["include_coding"]
        report, flow, _ = await complete(server, {**child, "access_token": a["access_token"]}, [theme], restart=True)
        assert report["revision_source"] == {"task_id": task["id"], "interview_id": sid, "theme": theme}
        saved = next(t for t in request(base, "/api/account/revision-tasks", headers=auth(a))["items"] if t["id"] == task["id"])
        assert (saved["status"], saved["completed_at"]) == (before["status"], before["completed_at"])
        assert saved["latest_practice"] == {"interview_id": child["interview_id"], "status": "finished"}
        assert request(base, f"/api/interview/{sid}/report", headers=headers) == source_report
        second = request(base, task_path + "/practice", {}, auth(a))
        assert not second["reused"] and second["interview_id"] != child["interview_id"]
        request(base, f'/api/interview/{second["interview_id"]}/cancel', {}, headers)
        third = request(base, task_path + "/practice", {}, auth(a))
        assert not third["reused"] and third["interview_id"] not in {child["interview_id"], second["interview_id"]}
        assert delete(base, f'/api/account/interviews/{third["interview_id"]}', auth(a))["deleted"]
        assert delete(base, f"/api/account/interviews/{sid}", auth(a))["deleted"]
        detached = request(base, f'/api/interview/{child["interview_id"]}/report', headers=headers)
        assert detached["is_complete"] and detached["answer_count"] == report["answer_count"] and detached["revision_source"] is None
        denied(base, task_path + "/practice", payload={}, headers=auth(a), status=404)
        cases.append({"position": position, "theme": theme, "manual_state_preserved": manual,
                      "practice": flow, "concurrent_requests": 4, "unique_initial_practices": 1,
                      "source_detached_child_preserved": True})
    assert request(base, "/api/account/revision-tasks", headers=auth(a))["total"] == 0
    assert delete(base, "/api/account", auth(a), {"password": password})["deleted"]
    assert request(base, "/api/auth/me", headers=auth(b))["username"] == "task_practice_other"
    return {"result": "passed", "synthetic_inputs_only": True, "external_model_calls": 0,
            "cases": cases, "restart_verified": 2, "concurrent_creation_deduplicated": True,
            "new_practice_after_finished_or_cancelled": True, "manual_status_not_auto_completed": True,
            "cross_account_isolation": True, "record_and_account_cleanup": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-task-practice-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "task-practice.sqlite3")
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
