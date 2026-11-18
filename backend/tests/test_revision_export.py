from datetime import datetime, timezone

from app.models.entities import QuestionMark, RevisionTask, RevisionNote
from tests.test_accounts import users, auth, owned
from tests.test_ws_recovery import api


def test_export_is_account_scoped_and_excludes_credentials(users):
    client, factory, first, second = users
    interview = owned(client, first)
    with factory() as db:
        db.add_all([
            QuestionMark(account_id=first['account']['id'], position='python_backend',
                         question_id='first-private', status='todo', version=0, created_at=datetime.now(timezone.utc)),
            QuestionMark(account_id=second['account']['id'], position='python_backend',
                         question_id='second-private', status='done', version=0, created_at=datetime.now(timezone.utc)),
        ])
        task = RevisionTask(account_id=first['account']['id'], interview_id=interview['interview_id'],
                            position='python_backend', theme='Python基础', source_score=3,
                            weak_score=4, focus_points=['概念'], status='todo')
        db.add(task)
        db.flush()
        db.add(RevisionNote(task_id=task.id, content='个人复习笔记', version=1))
        db.commit()
    assert client.get('/api/account/revision-export').status_code == 401
    response = client.get('/api/account/revision-export', headers=auth(first))
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert [item['question_id'] for item in response.json()['question_marks']] == ['first-private']
    assert response.json()['tasks'][0]['note'] == '个人复习笔记'
    assert 'second-private' not in response.text
    assert first['access_token'] not in response.text
    assert 'password_hash' not in response.text


def test_export_refuses_excessive_data_without_truncating(users):
    client, factory, first, _ = users
    with factory() as db:
        db.add_all(QuestionMark(account_id=first['account']['id'], position='python_backend',
            question_id=f'question-{index}', status='todo', version=0,
            created_at=datetime.now(timezone.utc)) for index in range(1001))
        db.commit()
    response = client.get('/api/account/revision-export', headers=auth(first))
    assert response.status_code == 413
    assert '上限' in response.json()['detail']
