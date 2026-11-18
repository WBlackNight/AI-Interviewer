import csv
import io
import re
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from app.models.entities import Account, AccountProfile, AdminAudit, AdminQuestionReview, Interview
from app.services import admin_operations as ops
from tests.test_admin import managed
from tests.test_accounts import users, auth
from tests.test_ws_recovery import api


def question(client, owner):
    return client.get('/api/admin/questions?limit=1', headers=auth(owner)).json()['items'][0]


def payload(row, **changes):
    return dict(status='approved', note='内容已核对', expected_version=row['review_version'],
                content_hash=row['content_hash'], **changes)


def test_readonly_role_cannot_export_review_or_inspect_audit(managed):
    client, factory, owner, viewer, config = managed
    config.admin_viewer_account_ids = viewer['account']['id']
    result = client.get('/api/admin/overview', headers=auth(viewer)).json()
    assert result['role'] == 'viewer' and not any(result['permissions'].values())
    assert client.get('/api/auth/me', headers=auth(viewer)).json()['is_admin']
    row = question(client, viewer)
    assert client.patch('/api/admin/questions/' + row['id'] + '/review', json=payload(row), headers=auth(viewer)).status_code == 403
    assert client.get('/api/admin/export?resource=accounts', headers=auth(viewer)).status_code == 403
    assert client.get('/api/admin/audit', headers=auth(viewer)).status_code == 403
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AdminAudit).where(AdminAudit.outcome == 'denied')) == 3
        assert db.scalar(select(func.count()).select_from(AdminQuestionReview)) == 0
    config.admin_viewer_account_ids = ''
    assert client.get('/api/admin/questions', headers=auth(viewer)).status_code == 403


def test_review_is_versioned_atomic_and_audited(managed):
    client, factory, owner, _, _ = managed
    row = question(client, owner)
    url = '/api/admin/questions/' + row['id'] + '/review'
    result = client.patch(url, json=payload(row), headers=auth(owner))
    assert result.status_code == 200, result.text
    assert result.json()['version'] == 1
    assert client.patch(url, json=payload(row), headers=auth(owner)).status_code == 409
    updated = question(client, owner)
    assert updated['review_status'] == 'approved' and updated['review_version'] == 1
    with factory() as db:
        saved = db.get(AdminQuestionReview, row['id'])
        assert saved.status == 'approved' and saved.version == 1
        audit = db.scalars(select(AdminAudit)).one()
        assert audit.action == 'question_review' and audit.request_id == result.headers['x-request-id']
        assert audit.details == {'from': 'pending', 'to': 'approved', 'version': 1}
    assert client.get('/api/admin/questions?review=approved', headers=auth(owner)).json()['total'] == 1
    audit_page = client.get('/api/admin/audit?action=question_review', headers=auth(owner)).json()
    assert audit_page['total'] == 1 and audit_page['items'][0]['actor'] == owner['account']['username']


def test_changed_question_invalidates_review_and_rejects_stale_content(managed, monkeypatch):
    client, _, owner, _, _ = managed
    from app.api import admin as routes
    assets = routes.load_assets(routes.get_settings())
    row = question(client, owner)
    client.patch('/api/admin/questions/' + row['id'] + '/review', json=payload(row), headers=auth(owner))
    changed = [replace(q, content=q.content + '（新版）') if q.id == row['id'] else q for q in assets[1].questions]
    monkeypatch.setattr(routes, 'load_assets', lambda _: (assets[0], SimpleNamespace(questions=changed)))
    updated = question(client, owner)
    assert updated['review_stale'] and updated['review_status'] == 'pending'
    stale = {**payload(row), 'expected_version': 1}
    assert client.patch('/api/admin/questions/' + row['id'] + '/review', json=stale, headers=auth(owner)).status_code == 409


@pytest.mark.parametrize('changes', [{'status': 'invalid'}, {'note': 'a' * 501}, {'status': 'needs_revision', 'note': '短'}, {'expected_version': True}, {'content_hash': 'bad'}])
def test_invalid_reviews_do_not_write(managed, changes):
    client, factory, owner, _, _ = managed
    row = question(client, owner)
    response = client.patch('/api/admin/questions/' + row['id'] + '/review', json={**payload(row), **changes}, headers=auth(owner))
    assert response.status_code == 422
    assert re.fullmatch('[a-f0-9]{32}', response.headers['x-request-id'])
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AdminQuestionReview)) == 0


def test_csv_uses_all_filtered_rows_and_does_not_leak_private_data(managed):
    client, factory, owner, _, _ = managed
    with factory() as db:
        db.add(AccountProfile(account_id=owner['account']['id'], nickname='=HYPERLINK("evil")', email='private@example.test'))
        db.commit()
    response = client.get('/api/admin/export?resource=accounts&bound=bound', headers=auth(owner))
    assert response.status_code == 200 and response.content.startswith(b'\xef\xbb\xbf')
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == 2 and rows[1][1].startswith("'=")
    assert response.headers['x-export-rows'] == '1'
    assert 'private@example.test' not in response.text and 'password_hash' not in response.text
    audit = client.get('/api/admin/audit?action=data_export&q=' + response.headers['x-request-id'], headers=auth(owner)).json()
    assert audit['total'] == 1 and audit['items'][0]['details']['rows'] == 1
    listing = client.get('/api/admin/questions?position=education&limit=1', headers=auth(owner)).json()
    exported = client.get('/api/admin/export?resource=questions&position=education', headers=auth(owner))
    assert int(exported.headers['x-export-rows']) == listing['total'] > 1
    assert 'answer_points' not in exported.text and 'testcases' not in exported.text


@pytest.mark.parametrize('value', ['=1+1', ' +SUM(A1)', '-1', '@SUM(A1)', '\tcalc', '\rline', '\nline'])
def test_csv_formula_prefixes_are_escaped(value):
    assert ops.csv_cell(value).startswith("'")
    assert ops.csv_cell('正常内容') == '正常内容'


def test_export_limit_is_explicit_and_not_silently_truncated(managed, monkeypatch):
    client, factory, owner, _, _ = managed
    monkeypatch.setattr(ops.admin, 'accounts', lambda *a, **k: {'total': 1001, 'items': []})
    response = client.get('/api/admin/export?resource=accounts', headers=auth(owner))
    assert response.status_code == 422 and '1000' in response.json()['detail']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 0


def test_date_filters_use_beijing_inclusive_days_and_sort(managed):
    client, factory, owner, _, _ = managed
    with factory() as db:
        owner_row = db.get(Account, owner['account']['id'])
        owner_row.created_at = datetime(2026, 11, 16, 16, 0)
        for index, hour in enumerate((0, 23)):
            local = datetime(2026, 11, 17, hour).replace(tzinfo=ops.admin.BEIJING).astimezone().replace(tzinfo=None)
            db.add(Interview(id=str(index) * 32, position='education', difficulty='mid', plan=[], status='running', started_at=local))
        db.commit()
    result = client.get('/api/admin/accounts?start=2026-11-17&end=2026-11-17&q=' + owner['account']['username'], headers=auth(owner)).json()
    assert result['total'] == 1
    result = client.get('/api/admin/interviews?start=2026-11-17&end=2026-11-17&sort=oldest', headers=auth(owner)).json()
    assert result['total'] == 2 and result['items'][0]['id'] == '0' * 32
    for path in ('accounts?start=2026-11-18&end=2026-11-17', 'accounts?end=9999-12-31', 'interviews?start=2026-02-30', 'questions?sort=oldest', 'export?resource=accounts&sort=difficulty'):
        assert client.get('/api/admin/' + path, headers=auth(owner)).status_code == 422


def test_admin_500_has_safe_message_and_correlatable_id(managed, monkeypatch):
    client, _, owner, _, _ = managed
    monkeypatch.setattr(ops.admin, 'overview', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('SECRET DATABASE URL')))
    response = client.get('/api/admin/overview', headers=auth(owner))
    assert response.status_code == 500 and 'SECRET' not in response.text
    assert re.fullmatch('[a-f0-9]{32}', response.headers['x-request-id'])
    assert response.headers['cache-control'] == 'no-store'
