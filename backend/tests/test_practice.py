import pytest
from sqlalchemy import func, select

from app.models.entities import Interview, QuestionScore
from tests.test_ws_recovery import api, answer, connect, receive_turn


def create_practice(client, position="python_backend", themes=None):
    response = client.post("/api/interview", json={"position": position,
        "difficulty": "hard", "themes": themes or ["Python基础"]})
    assert response.status_code == 200, response.text
    return response.json()


def finish_practice(client, created, allowed):
    main_ids = set()
    for _ in range(30):
        # 每轮重连，确保主题限制来自持久化大纲而非客户端内存。
        with connect(client, created) as (socket, snapshot):
            if snapshot["finished"]:
                break
            question = snapshot["current_question"]
            assert question["theme"] in allowed and not question.get("is_coding")
            if not question.get("is_probe"):
                assert question["id"] not in main_ids
                main_ids.add(question["id"])
            socket.send_json(answer(snapshot, text="我不会，请帮我指出缺口"))
            events = receive_turn(socket)
            assert events[-1]["type"] != "error", events
            if events[-1]["type"] == "report_ready":
                break
    else:
        pytest.fail("专项练习未在有界轮数内结束")
    headers = {"X-Interview-Token": created["access_token"]}
    report = client.get(f'/api/interview/{created["interview_id"]}/report', headers=headers).json()
    assert report["is_complete"] and report["weak_points"]
    assert report["question_count"] == len(main_ids)
    assert {q["theme"] for q in report["per_question"]} <= set(allowed)
    return report


@pytest.mark.parametrize("position,themes", [
    ("java_backend", ["MySQL", "Redis"]),
    ("python_backend", ["Python基础", "异步与并发"]),
])
def test_selected_scope_survives_reconnect_and_weak_retry(api, monkeypatch, position, themes):
    from app.api import routes
    client, factory = api
    monkeypatch.setattr(routes, "build_llm", lambda *a: pytest.fail("专项创建不能调用模型规划"))
    created = create_practice(client, position, themes)
    assert [p["theme"] for p in created["plan"]] == themes
    assert sum(p["weight"] for p in created["plan"]) == pytest.approx(1)
    assert all(1 <= p["question_count"] <= 2 and not p["include_coding"] for p in created["plan"])
    report = finish_practice(client, created, themes)
    assert report["practice_themes"] == report["weak_points"]
    path = f'/api/interview/{created["interview_id"]}/practice'
    assert client.post(path).status_code == 403
    response = client.post(path, headers={"X-Interview-Token": created["access_token"]})
    assert response.status_code == 200, response.text
    retry = response.json()
    assert retry["interview_id"] != created["interview_id"]
    assert retry["access_token"] != created["access_token"]
    assert retry["position"] == position
    assert [p["theme"] for p in retry["plan"]] == report["practice_themes"]
    assert all(p["difficulty"] == "hard" and not p["include_coding"] for p in retry["plan"])
    assert client.get(f'/api/interview/{retry["interview_id"]}/report',
                      headers={"X-Interview-Token": created["access_token"]}).status_code == 403
    with connect(client, retry) as (_, snapshot):
        assert snapshot["current_question"]["theme"] in report["practice_themes"]
    with factory() as db:
        row = db.get(Interview, retry["interview_id"])
        assert row.resume_id is None and row.user_id is None
        assert db.scalar(select(func.count()).select_from(QuestionScore).where(
            QuestionScore.interview_id == retry["interview_id"])) == 0


@pytest.mark.parametrize("themes", [[], ["Python基础", "Python基础"], ["MySQL"],
    ["算法与编码"], ["不存在"], [""], "Python基础",
    ["Python基础", "异步与并发", "Web与数据", "extra"], ["x"] * 13])
def test_invalid_themes_do_not_create_or_broaden_a_session(api, themes):
    client, factory = api
    assert client.post("/api/interview", json={"position": "python_backend", "themes": themes}).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 0


def test_topic_practice_rejects_resume_instead_of_parsing_it(api):
    client, _ = api
    assert client.post("/api/interview", json={"position": "python_backend",
        "themes": ["Python基础"], "resume_id": "not-authorized"}).status_code == 422


def test_retry_requires_finished_source_and_its_own_token(api):
    client, _ = api
    source, other = create_practice(client), create_practice(client)
    path = f'/api/interview/{source["interview_id"]}/practice'
    assert client.post(path, headers={"X-Interview-Token": other["access_token"]}).status_code == 403
    assert client.post(path, headers={"X-Interview-Token": source["access_token"]}).status_code == 409
    assert client.get(f'/api/interview/{source["interview_id"]}/report',
        headers={"X-Interview-Token": source["access_token"]}).json()["practice_themes"] == []


@pytest.mark.parametrize("theme,score", [("Python基础", 9), ("算法与编码", 0), ("已移除的主题", 0)])
def test_no_eligible_weak_topics_returns_explicit_error(api, theme, score):
    client, factory = api
    source = create_practice(client)
    with factory() as db:
        db.get(Interview, source["interview_id"]).status = "finished"
        db.add(QuestionScore(interview_id=source["interview_id"], question_id="fixture",
            theme=theme, score=score, dimensions={}))
        db.commit()
    headers = {"X-Interview-Token": source["access_token"]}
    base = f'/api/interview/{source["interview_id"]}'
    assert client.get(base + "/report", headers=headers).json()["practice_themes"] == []
    assert client.post(base + "/practice", headers=headers).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == 1


def test_catalog_only_offers_available_knowledge_topics_and_server_limit(api, monkeypatch):
    from app.api import routes
    client, _ = api
    monkeypatch.setattr(routes.settings, "max_plan_themes", 1)
    positions = {p["id"]: p for p in client.get("/api/positions").json()["positions"]}
    python = positions["python_backend"]
    assert python["practice_themes"] == ["Python基础", "异步与并发", "Web与数据"]
    assert python["practice_theme_limit"] == 1
    assert client.post("/api/interview", json={"position": "python_backend",
        "themes": ["Python基础", "异步与并发"]}).status_code == 422
