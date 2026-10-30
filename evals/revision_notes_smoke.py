"""离线真实HTTP笔记冒烟：并发版本、草稿边界、重启、独立登录与删除。"""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlencode
import uuid

from smoke_e2e import BACKEND, OPENER, Server, request
from practice_smoke import complete, denied
from account_smoke import delete
from revision_smoke import update


def put(base, path, headers, content, version, expected=(200,)):
    payload = {"content": content, "expected_version": version}
    req = urllib.request.Request(base + path, method="PUT",
        headers={"Content-Type": "application/json", **headers}, data=json.dumps(payload).encode())
    try:
        response = OPENER.open(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.code in expected, response.code
        assert response.headers["Cache-Control"] == "no-store"
        return response.code, json.loads(response.read())


async def run(server):
    password = "synthetic-notes-" + uuid.uuid4().hex
    owner, other = [request(server.base, "/api/auth/register", {"username": name, "password": password})
                    for name in ("notes_owner", "notes_other")]
    auth = lambda user: {"Authorization": "Bearer " + user["access_token"]}
    tasks, reports = [], []
    for position, theme in (("java_backend", "MySQL"), ("python_backend", "Python基础")):
        created = request(server.base, "/api/interview", {"position": position, "themes": [theme]}, auth(owner))
        report, _, _ = await complete(server, {**created, "access_token": owner["access_token"]}, [theme])
        reports.append(report)
        tasks.append(request(server.base, f'/api/account/interviews/{created["interview_id"]}/revision-tasks', {}, auth(owner))["items"][0])
    task_path = "/api/account/revision-tasks/" + tasks[0]["id"]
    path = task_path + "/note"
    original = update(server.base, task_path, auth(owner), {"status": "done", "due_date": "2026-10-25"})
    first = put(server.base, path, auth(owner), '<script>synthetic only</script>\r\n  保留缩进', 0)[1]
    assert first["version"] == 1 and first["content"].endswith("\n  保留缩进")
    second = request(server.base, "/api/auth/login", {"username": "notes_owner", "password": password})
    # 两个独立会话以同一版本同时写入，只允许一个成功。
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(put, server.base, path, auth(user), text, 1, (200, 409))
                   for user, text in ((owner, "页面A的新理解 100%"), (second, "页面B的新理解 100%"))]
        outcomes = [future.result() for future in futures]
    assert sorted(status for status, _ in outcomes) == [200, 409]
    winner = next(data for status, data in outcomes if status == 200)
    assert winner["version"] == 2
    assert put(server.base, path, auth(second), winner["content"], 2)[1] == winner
    search_path = '/api/account/revision-tasks?' + urlencode({'q': '%', 'note_filter': 'with'})
    searched = request(server.base, search_path, headers=auth(owner))
    assert searched['total'] == 1 and searched['items'][0]['id'] == tasks[0]['id']
    assert searched['counts'] == {'todo': 0, 'done': 1}
    assert request(server.base, '/api/account/revision-tasks?note_filter=without', headers=auth(owner))['total'] == 1
    assert request(server.base, search_path, headers=auth(other))['total'] == 0
    put(server.base, path, auth(other), "不可写入", 0, (404,))
    denied(server.base, path, headers=auth(other), status=404)
    put(server.base, path, {}, "不可写入", 0, (401,))
    await asyncio.to_thread(server.restart)
    login = request(server.base, "/api/auth/login", {"username": "notes_owner", "password": password})
    assert request(server.base, path, headers=auth(login)) == winner
    assert request(server.base, search_path, headers=auth(login))['total'] == 1
    current = request(server.base, "/api/account/revision-tasks?status=done", headers=auth(login))["items"][0]
    for key in ("status", "completed_at", "due_date", "source_score", "focus_points"):
        assert current[key] == original[key]
    assert current["note"] == winner
    assert request(server.base, f'/api/interview/{tasks[0]["interview_id"]}/report',
                   headers={"X-Interview-Token": login["access_token"]}) == reports[0]
    cleared = put(server.base, path, auth(login), "", 2)[1]
    assert cleared["version"] == 3 and cleared["content"] == ""
    assert request(server.base, search_path, headers=auth(login))['total'] == 0
    assert request(server.base, '/api/account/revision-tasks?note_filter=without', headers=auth(login))['total'] == 2
    put(server.base, path, auth(second), "旧草稿不能覆盖清空", 2, (409,))
    assert put(server.base, path, auth(login), "比较后合并的笔记", 3)[1]["version"] == 4
    other_path = "/api/account/revision-tasks/" + tasks[1]["id"] + "/note"
    put(server.base, other_path, auth(login), "随账户清理的笔记", 0)
    assert delete(server.base, f'/api/account/interviews/{tasks[0]["interview_id"]}', auth(login))["deleted"]
    denied(server.base, path, headers=auth(login), status=404)
    assert request(server.base, other_path, headers=auth(login))["version"] == 1
    assert delete(server.base, "/api/account", auth(login), {"password": password})["deleted"]
    assert request(server.base, "/api/auth/me", headers=auth(other))["username"] == "notes_other"
    return {"result": "passed", "synthetic_inputs_only": True, "external_model_calls": 0,
            "completed_reports": 2, "restart_verified": True, "independent_login": True,
            "concurrent_same_version_statuses": [200, 409], "plain_text_and_newlines": True,
            "same_content_idempotent": True, "clear_keeps_version": True,
            "scores_dates_status_unchanged": True, "cross_account_isolation": True,
            "source_and_account_deletion": True, "literal_search_and_note_filters": True,
            "search_counts_scoped": True, "search_persists_after_restart": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-notes-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "notes.sqlite3")
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
