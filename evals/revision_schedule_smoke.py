"""离线真实HTTP日期安排、重启、重新登录、筛选及删除冒烟。"""
import argparse
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import uuid

from smoke_e2e import BACKEND, Server, request
from practice_smoke import complete
from account_smoke import delete
from revision_smoke import update


async def run(server):
    password = "synthetic-schedule-" + uuid.uuid4().hex
    a, b = [request(server.base, "/api/auth/register", {"username": name, "password": password})
            for name in ("schedule_owner", "schedule_other")]
    auth = lambda user: {"Authorization": "Bearer " + user["access_token"]}
    today = date.fromisoformat(request(server.base, "/api/account/revision-tasks", headers=auth(a))["today"])
    dates = [(today - timedelta(days=2)).isoformat(), today.isoformat(), (today + timedelta(days=1)).isoformat(), None]
    tasks, reports = [], []
    for index, day in enumerate(dates):
        position, theme = ("java_backend", "MySQL") if index < 2 else ("python_backend", "Python基础")
        created = request(server.base, "/api/interview", {"position": position, "themes": [theme]}, auth(a))
        report, _, _ = await complete(server, {**created, "access_token": a["access_token"]}, [theme])
        reports.append(report)
        task = request(server.base, f'/api/account/interviews/{created["interview_id"]}/revision-tasks', {}, auth(a))["items"][0]
        tasks.append(update(server.base, "/api/account/revision-tasks/" + task["id"], auth(a), {"due_date": day}))
    path = "/api/account/revision-tasks"
    board = request(server.base, path + "?status=todo", headers=auth(a))
    assert board["date_counts"] == {"today": 1, "overdue": 1, "upcoming": 1, "unscheduled": 1}
    assert board["timezone"] == "Asia/Shanghai"
    for index, key in enumerate(("overdue", "today", "upcoming", "unscheduled")):
        result = request(server.base, path + "?status=todo&due=" + key, headers=auth(a))
        assert result["total"] == 1 and result["items"][0]["id"] == tasks[index]["id"]
    first = request(server.base, path + "?due=overdue&limit=1", headers=auth(a))
    assert first["has_more"] is False
    assert request(server.base, path + "?due=today&position=python_backend", headers=auth(a))["total"] == 0
    task_path = path + "/" + tasks[0]["id"]
    update(server.base, task_path, auth(b), {"due_date": None}, 404)
    update(server.base, task_path, auth(a), {"due_date": "2026-02-30", "status": "done"}, 422)
    done = update(server.base, task_path, auth(a), {"status": "done"})
    assert done["due_date"] == dates[0]
    await asyncio.to_thread(server.restart)
    login = request(server.base, "/api/auth/login", {"username": "schedule_owner", "password": password})
    recovered = request(server.base, path + "?status=done&due=overdue", headers=auth(login))
    assert recovered["items"] == [done]
    assert request(server.base, f'/api/account/interviews/{done["interview_id"]}/revision-tasks', {}, auth(login))["items"] == [done]
    moved = update(server.base, task_path, auth(login), {"due_date": dates[2]})
    assert moved["completed_at"] == done["completed_at"] and moved["status"] == "done"
    cleared = update(server.base, task_path, auth(login), {"due_date": None})
    assert cleared["due_date"] is None and cleared["status"] == "done"
    restored = update(server.base, task_path, auth(login), {"status": "todo", "due_date": dates[1]})
    assert restored["completed_at"] is None
    assert request(server.base, f'/api/interview/{done["interview_id"]}/report',
                   headers={"X-Interview-Token": login["access_token"]}) == reports[0]
    assert request(server.base, path, headers=auth(b))["total"] == 0
    assert delete(server.base, f'/api/account/interviews/{done["interview_id"]}', auth(login))["deleted"]
    assert request(server.base, path, headers=auth(login))["total"] == 3
    update(server.base, task_path, auth(login), {"due_date": dates[1]}, 404)
    assert delete(server.base, "/api/account", auth(login), {"password": password})["deleted"]
    return {"result": "passed", "synthetic_inputs_only": True, "external_model_calls": 0,
            "completed_reports": 4, "restart_verified": True, "independent_login": True,
            "date_views": ["today", "overdue", "upcoming", "unscheduled"], "timezone": "Asia/Shanghai",
            "reschedule_clear_restore": True, "manual_completion_preserved": True,
            "scores_unchanged": True, "cross_account_isolation": True, "source_and_account_deletion": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-schedule-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "schedule.sqlite3")
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
