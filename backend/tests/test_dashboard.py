from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models.entities import Interview, RevisionTask
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_revision_tasks import source, add


def dashboard(client, user):
    response = client.get('/api/account/dashboard', headers=auth(user))
    assert response.status_code == 200
    return response.json()


def test_empty_dashboard_has_explicit_zeroes_and_seven_calendar_days(users):
    client, _, a, _ = users
    result = dashboard(client, a)
    assert result['interviews'] == dict.fromkeys(['created', 'running', 'finished', 'cancelled'], 0)
    assert result['tasks'] == dict.fromkeys(['todo', 'done', 'today', 'overdue', 'upcoming', 'unscheduled'], 0)
    assert result['active'] == result['recent'] == result['priority_tasks'] == []
    assert len(result['week']) == 7 and sum(day['finished'] for day in result['week']) == 0
    assert result['week'][-1]['date'] == result['today'] and result['timezone'] == 'Asia/Shanghai'
    assert client.get('/api/account/dashboard').status_code == 401


def test_dashboard_scopes_all_counts_and_omits_private_content(users):
    client, factory, a, b = users
    first = source(factory, a, 1)
    task = add(client, a, first).json()['items'][0]
    client.put('/api/account/revision-tasks/' + task['id'] + '/note', headers=auth(a),
               json={'content': 'private note must not appear', 'expected_version': 0})
    source(factory, a, 2, status='running')
    other = source(factory, b, 3, status='running')
    add(client, b, source(factory, b, 4))
    result = dashboard(client, a)
    assert result['interviews'] == {'created': 0, 'running': 1, 'finished': 1, 'cancelled': 0}
    assert result['tasks']['todo'] == 1 and result['notes_with_content'] == 1
    assert result['recent'][0]['interview_id'] == first
    assert other not in str(result) and 'private note' not in str(result)
    assert 'private answer' not in str(result) and 'private question' not in str(result)


def test_week_uses_beijing_midnight_excludes_cancelled_and_future(users, monkeypatch):
    client, factory, a, _ = users
    monkeypatch.setattr('app.services.dashboard.revision_today', lambda: date(2026, 10, 25))
    moments = [datetime(2026, 10, 18, 15, 59, 59), datetime(2026, 10, 18, 16),
               datetime(2026, 10, 24, 15, 59, 59), datetime(2026, 10, 24, 16),
               datetime(2026, 10, 25, 16), None]
    for index, moment in enumerate(moments, 1):
        sid = source(factory, a, index)
        with factory() as db:
            db.get(Interview, sid).ended_at = moment.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None) if moment else None
            db.commit()
    cancelled = source(factory, a, 10, status='cancelled')
    with factory() as db:
        db.get(Interview, cancelled).ended_at = datetime(2026, 10, 24, 20, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        db.commit()
    result = dashboard(client, a)
    assert [day['finished'] for day in result['week']] == [1, 0, 0, 0, 0, 1, 1]
    assert result['interviews']['finished'] == 6 and result['interviews']['cancelled'] == 1


def test_priority_is_overdue_then_today_and_omits_done_future_unscheduled(users, monkeypatch):
    client, factory, a, _ = users
    today = date(2026, 10, 25)
    monkeypatch.setattr('app.services.dashboard.revision_today', lambda: today)
    due = [today, today - timedelta(days=3), None, today + timedelta(days=1), today - timedelta(days=1)]
    ids = []
    for index, day in enumerate(due, 1):
        item = add(client, a, source(factory, a, index)).json()['items'][0]
        ids.append(item['id'])
        response = client.patch('/api/account/revision-tasks/' + item['id'], headers=auth(a),
                                json={'due_date': day.isoformat() if day else None, 'status': 'done' if index == 5 else 'todo'})
        assert response.status_code == 200
    result = dashboard(client, a)
    assert result['tasks'] == {'todo': 4, 'done': 1, 'today': 1, 'overdue': 1, 'upcoming': 1, 'unscheduled': 1}
    assert [task['id'] for task in result['priority_tasks']] == [ids[1], ids[0]]


def test_dashboard_bounds_samples_and_does_not_change_state(users):
    client, factory, a, _ = users
    for index in range(1, 7):
        sid = source(factory, a, index, status='created' if index < 4 else 'running')
        assert sid
    for index in range(10, 16):
        add(client, a, source(factory, a, index))
    before = dashboard(client, a)
    assert len(before['active']) == len(before['recent']) == 3
    assert all(item['status'] == 'running' for item in before['active'])
    assert before == dashboard(client, a)
    with factory() as db:
        assert len(list(db.scalars(select(Interview).where(Interview.status == 'created')))) == 3
        assert all(task.status == 'todo' for task in db.scalars(select(RevisionTask)))


def test_deleting_source_and_clearing_note_updates_dashboard(users):
    client, factory, a, _ = users
    sid = source(factory, a, 1)
    task = add(client, a, sid).json()['items'][0]
    path = '/api/account/revision-tasks/' + task['id'] + '/note'
    client.put(path, headers=auth(a), json={'content': 'note', 'expected_version': 0})
    assert dashboard(client, a)['notes_with_content'] == 1
    client.put(path, headers=auth(a), json={'content': '', 'expected_version': 1})
    assert dashboard(client, a)['notes_with_content'] == 0
    assert client.delete('/api/account/interviews/' + sid, headers=auth(a)).status_code == 200
    result = dashboard(client, a)
    assert result['interviews']['finished'] == result['tasks']['todo'] == 0
    assert result['recent'] == []


def test_priority_sample_is_bounded_without_truncating_total(users):
    client, factory, a, _ = users
    today = dashboard(client, a)['today']
    for index in range(1, 7):
        item = add(client, a, source(factory, a, index)).json()['items'][0]
        client.patch('/api/account/revision-tasks/' + item['id'], headers=auth(a), json={'due_date': today})
    result = dashboard(client, a)
    assert result['tasks']['today'] == result['tasks']['todo'] == 6
    assert len(result['priority_tasks']) == result['limits']['priority_tasks'] == 4
