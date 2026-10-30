"""用本机假上游验证联调入口的资源白名单、授权头及错误传递。"""
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_home_gateway import create_gateway


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(port, path, method="GET", body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.fixture
def upstream():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append({"path": self.path, "method": self.command, "headers": dict(self.headers), "body": payload})
            self.send_response(401 if self.path == "/api/denied" else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public")
            self.end_headers()
            self.wfile.write(b'{"detail":"denied"}' if self.path == "/api/denied" else b'{"ok":true}')

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Handler)) as port:
        yield port, calls


def test_home_is_live_but_delivery_file_stays_offline(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, "/?audit=1")
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert b'<body data-api="/api" data-workspace-base="">' in body
        assert calls == []
        source = (Path(__file__).resolve().parents[1] / "index.html").read_bytes()
        assert b'<body data-api="" data-workspace-base="http://localhost:3000">' in source
        for path in ("/assets/home.css", "/assets/home.js"):
            assert request(gateway, path)[0] == 200
        assert calls == []


def test_voice_room_is_opt_in_with_same_interview_and_three_static_resources(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        path = '/interview/' + 'a' * 32
        normal = request(gateway, path)[2]
        voice = request(gateway, path + '?mode=voice')[2]
        assert b'/assets/interview.js' in normal and b'?mode=voice' in normal
        assert b'/assets/voice.js' in voice and b'data-ws-base="ws://localhost:' in voice
        assert request(gateway, '/assets/voice.js')[0] == 200
        realtime = request(gateway, path + '?mode=realtime')[2]
        assert b'/assets/realtime.js' in realtime and b'data-ws-base="ws://localhost:' in realtime
        assert request(gateway, '/assets/realtime.js')[0] == 200
        assert b'/assets/interview.js' in request(gateway, path + '?mode=wrong')[2]
        assert request(gateway, '/interview/invalid?mode=voice')[0] == 404
        assert calls == []


def test_page_aliases_redirect_without_losing_filters_or_interview_mode(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        cases = {
            '/index.html': '/',
            '/catalog.html?position=python_backend&theme=async': '/catalog?position=python_backend&theme=async',
            '/plans/?plan_id=example': '/plans?plan_id=example',
            '/revision-notes.html': '/notes',
            '/interview/' + 'a' * 32 + '/?mode=realtime': '/interview/' + 'a' * 32 + '?mode=realtime',
            '/report/' + 'b' * 32 + '/': '/report/' + 'b' * 32,
        }
        for source, destination in cases.items():
            status, headers, body = request(gateway, source)
            assert status == 308 and headers['Location'] == destination and not body
            assert request(gateway, source, 'HEAD')[0] == 308
            assert request(gateway, destination)[0] == 200
        assert request(gateway, '/catalog/', 'POST', b'{}')[0] == 405
        for path in ('/unknown/', '/assets/home.css/', '/interview/invalid/', '/voice.html', '/realtime.html', '/report.html'):
            assert request(gateway, path)[0] == 404
        assert calls == []


@pytest.mark.parametrize("path", ["/backend/.env", "/README.md", "/assets/README.md", "/.git/config", "/interview/invalid", "/not-found"])
def test_private_files_and_unknown_routes_are_not_served(upstream, path):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, path)[0] == 404
        assert calls == []


@pytest.mark.parametrize("path", ["/assets/%2e%2e/backend/.env", "/_next/../backend/.env", "/%5cbackend/.env", "http://example.invalid/api/positions"])
def test_traversal_and_absolute_targets_are_rejected(upstream, path):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, path)[0] == 400
        assert calls == []


def test_api_preserves_credentials_json_status_and_query_without_retry(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        payload = json.dumps({"position": "python_backend", "themes": ["Python基础"]}).encode()
        status, headers, _ = request(gateway, "/api/interview", "POST", payload,
            {"Authorization": "Bearer synthetic-token", "X-Resume-Token": "synthetic-resume", "Content-Type": "application/json"})
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert len(calls) == 1 and calls[0]["body"] == payload
        assert calls[0]["headers"]["Authorization"] == "Bearer synthetic-token"
        assert calls[0]["headers"]["X-Resume-Token"] == "synthetic-resume"
        assert request(gateway, "/api/denied")[0] == 401
        assert request(gateway, "/api/account/revision-tasks?due=today&status=todo")[0] == 200
        assert calls[-1]["path"] == "/api/account/revision-tasks?due=today&status=todo"


def test_workspace_pages_and_rsc_headers_reach_frontend(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, "/legacy-interview/" + "a" * 32 + "?_rsc=sample", headers={"RSC": "1"})[0] == 200
        assert calls[-1]["headers"]["RSC"] == "1"
        assert calls[-1]['path'] == '/interview/' + 'a' * 32 + '?_rsc=sample'
        assert request(gateway, "/workspace")[0] == 200 and calls[-1]["path"] == "/"
        assert request(gateway, "/_next/static/chunks/example.js")[0] == 200


def test_writes_to_pages_and_oversized_requests_are_rejected(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, "/", "POST", b"{}")[0] == 405
        assert request(gateway, "/account", "POST", b"{}")[0] == 405
        assert request(gateway, "/api/resume", "POST", headers={"Content-Length": str(7 * 1024 * 1024)})[0] == 413
        assert request(gateway, "/api/resume", "POST", headers={"Content-Length": "invalid"})[0] == 400
        assert calls == []


def test_unavailable_upstream_has_fixed_error_without_details():
    temporary = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    closed_port = temporary.server_port
    temporary.server_close()
    with running(create_gateway(0, closed_port, closed_port)) as gateway:
        status, _, body = request(gateway, "/api/positions")
        assert status == 502 and b"127.0.0.1" not in body and b"Traceback" not in body


def test_native_note_page_assets_and_put_forwarding(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, "/notes")[0] == 200
        assert request(gateway, "/assets/revision-notes.js")[0] == 200
        assert calls == []
        body = b'{"content":"synthetic-note","expected_version":0}'
        assert request(gateway, "/api/account/revision-tasks/example/note", "PUT", body,
                       {"Authorization": "Bearer synthetic-token"})[0] == 200
        assert calls[-1]["method"] == "PUT" and calls[-1]["body"] == body


def test_native_revision_board_and_script_are_local(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, "/revision")
        assert status == 200 and b'revision-board.js' in body
        assert headers['Cache-Control'] == 'no-store'
        assert request(gateway, "/assets/revision-board.js")[0] == 200
        assert request(gateway, "/revision", "PATCH", b'{}')[0] == 405
        assert calls == []


def test_existing_revision_board_remains_available_as_fallback(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert request(gateway, '/legacy-revision?status=done')[0] == 200
        assert calls[-1]['path'] == '/revision?status=done'


@pytest.mark.parametrize('path, script', [('/account', 'account.js'), ('/history', 'history.js')])
def test_native_account_history_pages_and_legacy_fallback(upstream, path, script):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, path)
        assert status == 200 and script.encode() in body and headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/' + script)[0] == 200
        assert request(gateway, path, 'POST', b'{}')[0] == 405
        assert calls == []
        assert request(gateway, '/legacy-' + path[1:])[0] == 200
        assert calls[-1]['path'] == path


@pytest.mark.parametrize('path, script, legacy', [
    ('/review', 'review.js', '/legacy-review'),
    ('/report/' + 'a' * 32, 'report.js', '/legacy-report/' + 'a' * 32),
])
def test_native_report_review_and_legacy_fallback(upstream, path, script, legacy):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, path + '?theme=MySQL')
        assert status == 200 and script.encode() in body
        assert headers['Cache-Control'] == 'no-store'
        assert request(gateway, path, 'HEAD')[2] == b''
        assert request(gateway, '/assets/' + script)[0] == 200
        assert request(gateway, path, 'POST', b'{}')[0] == 405
        assert calls == []
        assert request(gateway, legacy + '?theme=MySQL')[0] == 200
        assert calls[-1]['path'] == path + '?theme=MySQL'


def test_native_studio_uses_explicit_loopback_ws_without_forwarding_html(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        path = '/interview/' + 'b' * 32
        status, headers, body = request(gateway, path)
        assert status == 200 and b'interview.js' in body
        assert f'data-ws-base="ws://localhost:{port}"'.encode() in body
        assert headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/interview.js')[0] == 200
        assert request(gateway, path, 'POST', b'{}')[0] == 405
        assert calls == []
        assert request(gateway, '/legacy-interview/' + 'b' * 32)[0] == 200
        assert calls[-1]['path'] == path


def test_dashboard_page_and_script_are_static_and_not_an_api_alias(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert b'dashboard.js' in request(gateway, '/dashboard')[2]
        assert request(gateway, '/assets/dashboard.js')[0] == 200
        assert request(gateway, '/dashboard', 'PUT', b'{}')[0] == 405
        assert calls == []


def test_catalog_is_local_and_keeps_api_reads_separate(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, '/catalog?position=java_backend')
        assert status == 200 and b'catalog.js' in body and headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/catalog.js')[0] == 200
        assert request(gateway, '/catalog', 'POST', b'{}')[0] == 405
        assert calls == []
        assert request(gateway, '/api/catalog?position=java_backend&kind=coding')[0] == 200
        assert calls[-1]['path'] == '/api/catalog?position=java_backend&kind=coding'


def test_question_library_static_route_and_account_api(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, '/library')
        assert status == 200 and b'library.js' in body and headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/library.js')[0] == 200 and calls == []
        assert request(gateway, '/library', 'POST', b'{}')[0] == 405
        assert request(gateway, '/api/account/question-marks')[0] == 200
        assert calls[-1]['path'] == '/api/account/question-marks'


def test_coverage_static_route_and_public_api(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, '/coverage?position=java_backend')
        assert status == 200 and b'coverage.js' in body and headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/coverage.js')[0] == 200 and calls == []
        assert request(gateway, '/coverage', 'POST', b'{}')[0] == 405
        assert request(gateway, '/api/catalog/coverage?position=java_backend')[0] == 200
        assert calls[-1]['path'] == '/api/catalog/coverage?position=java_backend'


def test_preparation_page_and_account_api_are_separate(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        assert b'plans.js' in request(gateway, '/plans')[2]
        assert request(gateway, '/assets/plans.js')[0] == 200 and calls == []
        assert request(gateway, '/plans', 'POST', b'{}')[0] == 405
        assert request(gateway, '/api/account/preparation-plans?status=active')[0] == 200
        assert calls[-1]['path'] == '/api/account/preparation-plans?status=active'


def test_plan_history_route_keeps_static_and_private_queries_separate(upstream):
    port, calls = upstream
    with running(create_gateway(0, port, port)) as gateway:
        status, headers, body = request(gateway, '/plan-history?plan_id=' + 'a'*32 + '&status=finished&page=2')
        assert status == 200 and b'plan-history.js' in body and headers['Cache-Control'] == 'no-store'
        assert request(gateway, '/assets/plan-history.js')[0] == 200 and calls == []
        assert request(gateway, '/plan-history', 'POST', b'{}')[0] == 405
        assert request(gateway, '/api/account/preparation-plans/' + 'a'*32 + '/practices?status=finished')[0] == 200
        assert calls[-1]['path'].endswith('/practices?status=finished')
