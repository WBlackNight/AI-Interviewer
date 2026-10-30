"""隔离HTTP/WS取消冒烟：在途消息、重启、旧资产快照、认领、部分报告及删除。

python evals/cancellation_smoke.py --json-out docs/logs/cancel-local.json
仅使用合成账户/回答和离线评分；快照故障注入仅修改本脚本临时数据库。
"""
import argparse
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import uuid

import websockets

from smoke_e2e import BACKEND, Server, request
from practice_smoke import denied
from account_smoke import delete


async def snapshot(server, item, token):
    url = server.base.replace("http", "ws", 1) + f'/ws/interview/{item["interview_id"]}'
    async with websockets.connect(url, subprotocols=["interview", token]) as socket:
        await socket.send(json.dumps({"type": "start"}))
        return json.loads(await asyncio.wait_for(socket.recv(), 20))


async def run(server):
    base = server.base
    password = "synthetic-cancel-password-" + uuid.uuid4().hex
    account = request(base, "/api/auth/register", {"username": "cancel_owner", "password": password})
    auth = {"Authorization": "Bearer " + account["access_token"]}
    account_resource = {"X-Interview-Token": account["access_token"]}
    anonymous = request(base, "/api/interview", {"position": "java_backend", "themes": ["MySQL"]})
    interview_id, token = anonymous["interview_id"], anonymous["access_token"]
    headers = {"X-Interview-Token": token}
    url = base.replace("http", "ws", 1) + f"/ws/interview/{interview_id}"
    async with websockets.connect(url, subprotocols=["interview", token]) as socket:
        await socket.send(json.dumps({"type": "start"}))
        state = json.loads(await asyncio.wait_for(socket.recv(), 20))
        message = {"type": "answer", "message_id": uuid.uuid4().hex, "text": "我还不清楚，请指出需要补充的概念",
                   "turn_id": state["current_question"]["turn_id"], "version": state["version"]}
        await socket.send(json.dumps(message))
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 20))
            assert event["type"] != "error", event
            if event["type"] == "question":
                break
        denied(base, f"/api/interview/{interview_id}/cancel", payload={}, headers=account_resource)
        cancelled = request(base, f"/api/interview/{interview_id}/cancel", {}, headers)
        assert cancelled["changed"] and cancelled["status"] == "cancelled"
        again = request(base, f"/api/interview/{interview_id}/cancel", {}, headers)
        assert not again["changed"] and again["version"] == cancelled["version"]
        await socket.send(json.dumps(message))
        terminal = json.loads(await asyncio.wait_for(socket.recv(), 20))
        assert terminal["cancelled"] and terminal["current_question"] is None
        assert sum(e["type"] == "score" for e in terminal["events"]) == 1
    await asyncio.to_thread(server.restart)
    restored = await snapshot(server, anonymous, token)
    assert restored["cancelled"] and restored["finished"]
    report = request(base, f"/api/interview/{interview_id}/report", headers=headers)
    assert report["is_cancelled"] and not report["is_complete"] and report["answer_count"] == 1
    assert report["practice_themes"] == [] and report["scoring_sources"] == {"heuristic": 1}
    assert request(base, f"/api/interview/{interview_id}/report/export?format=json", headers=headers) == report
    denied(base, f"/api/interview/{interview_id}/practice", payload={}, headers=headers, status=409)
    request(base, f"/api/account/interviews/{interview_id}/claim", {"access_token": token}, auth)
    assert request(base, "/api/account/interviews", headers=auth)["items"][0]["status"] == "cancelled"
    assert request(base, "/api/account/review", headers=auth)["total"] == 0
    assert delete(base, f"/api/account/interviews/{interview_id}", auth)["deleted"]

    old = request(base, "/api/interview", {"position": "python_backend", "themes": ["Python基础"]}, auth)
    assert (await snapshot(server, old, account["access_token"]))["type"] == "snapshot"
    # 已验证临时路径属于本项目backend，故障注入不接触原开发库。
    assert server.db_path.resolve().is_relative_to(BACKEND.resolve())
    with closing(sqlite3.connect(server.db_path)) as database:
        raw = database.execute("SELECT snapshot FROM interview_runtime WHERE interview_id=?", (old["interview_id"],)).fetchone()[0]
        broken = {**json.loads(raw), "asset_version": "injected-retired-assets"}
        database.execute("UPDATE interview_runtime SET snapshot=? WHERE interview_id=?", (json.dumps(broken), old["interview_id"]))
        database.commit()
    assert (await snapshot(server, old, account["access_token"]))["code"] == "assets_changed"
    assert request(base, f'/api/interview/{old["interview_id"]}/cancel', {}, account_resource)["changed"]
    await asyncio.to_thread(server.restart)
    assert (await snapshot(server, old, account["access_token"]))["cancelled"]
    assert delete(base, "/api/account", auth, {"password": password})["deleted"]
    return {"result": "passed", "external_model_calls": 0, "synthetic_inputs_only": True,
            "cancel_idempotent": True, "anonymous_and_account_authorization": True,
            "existing_socket_terminal": True, "restart_verified": 2,
            "committed_answers_preserved": 1, "json_partial_export_verified": True,
            "cancelled_excluded_from_completed_review": True, "cancelled_practice_denied": True,
            "stale_assets_cancelled_without_restore": True, "claim_and_delete_cancelled": True,
            "account_delete_after_cancel": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-cancel-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "cancel.sqlite3")
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
