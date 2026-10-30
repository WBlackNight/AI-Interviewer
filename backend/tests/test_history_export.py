import json
import re

import pytest
from sqlalchemy import select

from app.models.entities import Interview
from app.services.report_export import render_markdown
from tests.test_ws_recovery import api, create, connect, answer, receive_turn


def headers(interview):
    return {"X-Interview-Token": interview["access_token"]}


@pytest.mark.parametrize("path", ["", "/report/export?format=markdown", "/report/export?format=json"])
def test_new_endpoints_reject_missing_or_other_interview_access(api, path):
    client, _ = api
    first, second = create(client), create(client)
    url = f"/api/interview/{first['interview_id']}{path}"
    assert client.get(url).status_code == 403
    assert client.get(url, headers=headers(second)).status_code == 403
    assert client.get(url, headers=headers(first)).status_code == 200


def test_summary_is_readonly_and_does_not_trigger_models(api, monkeypatch):
    from app.api import routes
    client, _ = api
    interview = create(client)
    def forbidden(*args, **kw): pytest.fail("read-only feature must not build models or search")
    monkeypatch.setattr(routes, "build_llm", forbidden)
    response = client.get(f"/api/interview/{interview['interview_id']}", headers=headers(interview))
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["status"] == "created" and data["answer_count"] == 0
    assert data["theme_count"] > 0 and data["last_activity_at"] is None
    assert not {"access_token", "user_id", "resume_id", "answer_text", "raw_text"} & data.keys()


def test_summary_updates_after_turn_without_opening_ws_on_read(api):
    client, _ = api
    interview = create(client)
    with connect(client, interview) as (socket, snapshot):
        socket.send_json(answer(snapshot))
        assert any(event["type"] == "score" for event in receive_turn(socket))
    data = client.get(f"/api/interview/{interview['interview_id']}", headers=headers(interview)).json()
    assert data["answer_count"] == 1 and data["status"] == "running"
    assert data["started_at"].endswith("+00:00") and data["last_activity_at"].endswith("+00:00")


@pytest.mark.parametrize("finished", [False, True])
def test_report_download_uses_same_authorized_report_and_marks_partial(api, finished):
    client, factory = api
    interview = create(client)
    if finished:
        with factory() as db:
            row = db.get(Interview, interview["interview_id"])
            row.status = "finished"
            db.commit()
    base = f"/api/interview/{interview['interview_id']}/report"
    report = client.get(base, headers=headers(interview)).json()
    response = client.get(base + "/export?format=json", headers=headers(interview))
    assert response.json() == report and response.json()["is_complete"] is finished
    assert response.headers["content-disposition"].endswith('.json"')
    response = client.get(base + "/export?format=markdown", headers=headers(interview))
    assert response.status_code == 200 and "面试复盘报告" in response.text
    assert ("已完成" if finished else "进行中（部分报告）") in response.text
    assert "尚无已评分回答" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert interview["access_token"] not in response.text
    assert client.get(base + "/export?format=html", headers=headers(interview)).status_code == 422


def test_export_preserves_answer_and_code_without_executable_markdown(api):
    client, _ = api
    interview = create(client)
    text = '<script>alert("x")</script>\n```\n# injected\n````\n[link](javascript:alert(1))'
    with connect(client, interview) as (socket, snapshot):
        socket.send_json(answer(snapshot, text=text))
        receive_turn(socket)
    base = f"/api/interview/{interview['interview_id']}/report"
    report = client.get(base, headers=headers(interview)).json()
    export = client.get(base + "/export", headers=headers(interview))
    assert report["per_question"][0]["answer_text"] == text
    # 原文完整保存，但处于比原文所有围栏更长的代码块内。
    assert f"`````text\n{text}\n`````" in export.text
    report["position"] = "<img src=x> [link](javascript:x)\n# header"
    rendered = render_markdown(report)
    assert "<img" not in rendered and "&lt;img" in rendered
    assert "\n# header" not in rendered
