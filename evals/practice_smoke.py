"""离线真实HTTP/WS：双岗位专项→低分报告→薄弱项复练，含进程重启和幂等补发。

python evals/practice_smoke.py --json-out docs/logs/practice-local.json
默认使用已构建的hash混合检索索引；不调用外部Embedding或LLM。
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.error
import uuid

import websockets

from smoke_e2e import BACKEND, ROOT, Server, request


def denied(base, path, *, headers=None, payload=None, status=403):
    try:
        request(base, path, payload, headers)
    except urllib.error.HTTPError as exc:
        assert exc.code == status, exc.code
    else:
        raise AssertionError("请求应被拒绝")


async def complete(server, created, themes, *, restart=False):
    base = server.base
    interview_id, token = created["interview_id"], created["access_token"]
    url = base.replace("http", "ws", 1) + f"/ws/interview/{interview_id}"
    headers = {"X-Interview-Token": token}
    pending, expected, answered = None, None, 0
    main_ids = set()
    restarted, retrieval_snapshots = False, []
    for _ in range(40):
        async with websockets.connect(url, subprotocols=["interview", token]) as ws:
            await ws.send(json.dumps({"type": "start"}))
            state = json.loads(await asyncio.wait_for(ws.recv(), 20))
            assert state["type"] == "snapshot", state
            if expected:
                assert state["current_question"] == expected
            if pending:
                await ws.send(json.dumps(pending))
                while True:
                    replay = json.loads(await asyncio.wait_for(ws.recv(), 20))
                    assert replay["type"] != "error", replay
                    if replay["type"] in ("question", "report_ready"):
                        break
                pending = None
            if state["finished"]:
                assert sum(e["type"] == "score" for e in state["events"]) == answered
                break
            q = state["current_question"]
            assert q["theme"] in themes and not q.get("is_coding"), q
            if not q.get("is_probe"):
                assert q["id"] not in main_ids
                main_ids.add(q["id"])
            pending = {"type": "answer", "message_id": uuid.uuid4().hex,
                       "turn_id": q["turn_id"], "version": state["version"],
                       "text": "我不会，请指出需要补充的概念"}
            await ws.send(json.dumps(pending))
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 20))
                assert event["type"] != "error", event
                if event["type"] == "score":
                    answered += 1
                if event["type"] in ("question", "report_ready"):
                    expected = event if event["type"] == "question" else None
                    break
        if restart and not restarted:
            retrieval_snapshots.append(request(base, "/api/diagnostics/retrieval"))
            await asyncio.to_thread(server.restart)
            restarted = True
    else:
        raise AssertionError("未在限定轮数内完成")
    report = request(base, f"/api/interview/{interview_id}/report", headers=headers)
    assert report["is_complete"] and report["answer_count"] == answered
    assert report["question_count"] == len(main_ids)
    assert {q["theme"] for q in report["per_question"]} <= set(themes)
    assert report["practice_themes"] and report["overall"] < report["weak_score"]
    exported = request(base, f"/api/interview/{interview_id}/report/export?format=json", headers=headers)
    assert exported == report
    retrieval_snapshots.append(request(base, "/api/diagnostics/retrieval"))
    return report, {"questions": report["question_count"], "answers": answered,
                    "restart_verified": restarted, "scope_verified": True,
                    "reconnect_and_idempotency": True, "json_export_verified": True}, retrieval_snapshots


async def run(server):
    positions = request(server.base, "/api/positions")["positions"]
    results = []
    for position in ("java_backend", "python_backend"):
        option = next(p for p in positions if p["id"] == position)
        themes = option["practice_themes"][:1]
        created = request(server.base, "/api/interview", {
            "position": position, "difficulty": "hard", "themes": themes})
        assert [p["theme"] for p in created["plan"]] == themes
        assert all(not p["include_coding"] for p in created["plan"])
        path = f'/api/interview/{created["interview_id"]}/practice'
        headers = {"X-Interview-Token": created["access_token"]}
        denied(server.base, path, payload={}, status=403)
        denied(server.base, path, payload={}, headers=headers, status=409)
        report, source_result, source_retrieval = await complete(server, created, themes, restart=True)
        retry = request(server.base, path, {}, headers)
        assert retry["interview_id"] != created["interview_id"]
        assert retry["access_token"] != created["access_token"]
        assert retry["position"] == position
        assert [p["theme"] for p in retry["plan"]] == report["practice_themes"]
        denied(server.base, f'/api/interview/{retry["interview_id"]}/report', headers=headers)
        retry_report, retry_result, retry_retrieval = await complete(
            server, retry, report["practice_themes"], restart=True)
        # 每个complete末尾与下一个重启前可能重复累计；这里只断言各快照零回退/零网络。
        for row in source_retrieval + retry_retrieval:
            assert row.get("counts", {}).get("fallback", 0) == 0
            assert row.get("embedding_usage", {}).get("network_calls", 0) == 0
        results.append({"position": position, "themes": themes, "source": source_result,
                        "retry": retry_result, "independent_access_verified": True,
                        "source_overall": report["overall"], "retry_overall": retry_report["overall"]})
    assert not request(server.base, "/api/diagnostics/llm")["llm_configured"]
    return {"result": "passed", "retrieval": server.retrieval_provider,
            "embedding": "hash", "external_model_calls": 0, "retrieval_fallbacks": 0,
            "synthetic_inputs_only": True, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", choices=["bm25", "hybrid"], default="hybrid")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".smoke-practice-", dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / "practice.sqlite3",
                        retrieval_provider=args.retrieval,
                        index_path=ROOT / "data/retrieval/question_index.json")
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
