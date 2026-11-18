from dataclasses import replace

from sqlalchemy import select, func

from app.models.entities import Interview
from app.score_origin import question_version
from tests.test_accounts import users, auth, resource
from tests.test_ws_recovery import api, connect, answer, receive_turn
from tests.test_score_origin_review import add_session, record


def original(factory, user):
    from app.api import routes
    _, bank = routes.load_assets(routes.settings)
    question = next(q for q in bank if q.position == "java_backend" and not q.is_coding)
    score = replace(record(question.id, version=question_version(question), theme=question.theme),
                    content=question.content, answer_text="上次回答")
    sid = add_session(factory, user["account"]["id"], 1, [score])
    return sid, question


def test_exact_question_retry_reuses_active_session_and_compares_answers(users):
    client, factory, a, b = users
    sid, question = original(factory, a)
    path = f"/api/interview/{sid}/question-practice"
    payload = {"question_id": question.id}
    report = client.get(f"/api/interview/{sid}/report", headers=resource(a)).json()
    assert report["per_question"][0]["can_retry"]
    assert client.post(path, json=payload).status_code == 401
    assert client.post(path, json=payload, headers=auth(b)).status_code == 404
    response = client.post(path, json=payload, headers=auth(a))
    assert response.status_code == 200, response.text
    retry = response.json()
    assert retry["account_owned"] and retry["access_token"] is None
    assert retry["plan"][0]["question_id"] == question.id
    assert client.post(path, json=payload, headers=auth(a)).json()["interview_id"] == retry["interview_id"]
    with connect(client, {**retry, "access_token": a["access_token"]}) as (socket, state):
        assert state["current_question"]["id"] == question.id
        assert state["current_question"]["content"] == question.content
    with connect(client, {**retry, "access_token": a["access_token"]}) as (socket, state):
        assert state["current_question"]["id"] == question.id
        socket.send_json(answer(state, text="跳过"))
        assert receive_turn(socket)[-1]["type"] == "report_ready"
    result = client.get(f'/api/interview/{retry["interview_id"]}/report', headers=resource(a))
    comparison = result.json()["retry_comparison"]
    assert comparison["original"]["answer_text"] == "上次回答"
    assert comparison["current"]["answer_text"] == "跳过"
    assert client.get(f'/api/interview/{retry["interview_id"]}/report', headers=resource(b)).status_code == 403
    assert client.get(f"/api/interview/{sid}/report", headers=resource(a)).json()["per_question"][0]["answer_text"] == "上次回答"


def test_retry_rejects_unknown_changed_or_unfinished_source(users):
    client, factory, a, _ = users
    sid, question = original(factory, a)
    path = f"/api/interview/{sid}/question-practice"
    assert client.post(path, json={"question_id": "missing"}, headers=auth(a)).status_code == 422
    from app.models.entities import QuestionScore
    with factory() as db:
        row = db.scalar(select(QuestionScore).where(QuestionScore.interview_id == sid))
        row.content = "题干已变更"
        db.commit()
        before = db.scalar(select(func.count()).select_from(Interview))
    assert client.post(path, json={"question_id": question.id}, headers=auth(a)).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Interview)) == before
        db.get(Interview, sid).status = "running"
        db.commit()
    assert client.post(path, json={"question_id": question.id}, headers=auth(a)).status_code == 409
