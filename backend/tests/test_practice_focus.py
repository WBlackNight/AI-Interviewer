from tests.test_accounts import users, auth
from tests.test_ws_recovery import api
from tests.test_score_origin_review import add_session, record


def focus(client, account):
    result = client.get('/api/account/dashboard', headers=auth(account))
    assert result.status_code == 200
    return result.json()['practice_focus']


def test_focus_is_empty_until_completed_scores_exist_and_is_account_scoped(users):
    client, factory, a, b = users
    assert focus(client, a) is None
    add_session(factory, b['account']['id'], 3, [record(theme='PRIVATE_OTHER')])
    add_session(factory, a['account']['id'], 2, [record()], status='running')
    add_session(factory, a['account']['id'], 4, [record()], status='cancelled')
    assert focus(client, a) is None
    own = add_session(factory, a['account']['id'], 1, [record(value=3)])
    result = focus(client, a)
    assert result['interview_id'] == own
    assert result['sample_count'] == 1 and result['local_feedback']
    assert result['themes'] == [{'name': 'MySQL', 'score': 3, 'question_count': 1,
                                 'can_practice': True, 'priority': True}]
    assert all(value not in str(result) for value in ['PRIVATE_OTHER', 'private answer', 'private question'])


def test_focus_matches_report_aggregation_and_follows_latest_completed_session(users):
    client, factory, a, _ = users
    own = add_session(factory, a['account']['id'], 1, [record('a', 0), record('a#p1', 10),
        record('a#p2', 10), record('b', 10), record('c', 3, theme='Redis')])
    result = focus(client, a)
    report = client.get('/api/interview/' + own + '/report',
                        headers={'X-Interview-Token': a['access_token']}).json()
    assert {item['name']: item['score'] for item in result['themes']} == report['theme_avg']
    assert result['sample_count'] == 3  # main questions, not five rounds
    assert result['themes'][0]['name'] == 'Redis'
    assert result['themes'][1]['score'] == 8.3
    latest = add_session(factory, a['account']['id'], 2, [record('fresh', 9, source='llm')])
    result = focus(client, a)
    assert result['interview_id'] == latest and not result['local_feedback']
    assert not result['themes'][0]['priority']
    # Removing the newest interview restores the previous saved practice focus.
    assert client.delete('/api/account/interviews/' + latest, headers=auth(a)).status_code == 200
    assert focus(client, a)['interview_id'] == own
