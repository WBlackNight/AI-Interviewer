"""本机联调入口：原生首页与已有Next.js服务同源，不是生产反向代理。"""
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re
from urllib.parse import unquote, urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 6 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}


def native_files():
    """Use the same explicit page/asset registry as the native builder."""
    manifest = json.loads((ROOT / 'ui/manifest.json').read_text(encoding='utf-8'))
    files = {'/assets/home.css': ('assets/home.css', 'text/css; charset=utf-8')}
    for name in manifest.get('shared_scripts',[]):
        assert re.fullmatch(r'[a-z-]+\.js',name)
        files['/assets/'+name]=('assets/'+name,'text/javascript; charset=utf-8')
    for page in manifest['pages']:
        assert re.fullmatch(r'[a-z-]+\.html', page['template'])
        assert re.fullmatch(r'[a-z-]+\.js', page['script'])
        if page['route']:
            assert re.fullmatch(r'/(?:[a-z-]+)?', page['route'])
            files[page['route']] = (page['template'], 'text/html; charset=utf-8')
        asset = 'assets/' + page['script']
        files['/' + asset] = (asset, 'text/javascript; charset=utf-8')
    files['/index.html'] = files['/']
    return files


def create_gateway(port, frontend_port=3100, backend_port=8000):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # 不记录请求头、正文或凭据。
            pass

        def send_bytes(self, status, body, content_type, headers=()):
            self.send_response(status)
            for key, value in headers:
                if key.lower() not in HOP_HEADERS | {"content-type", "cache-control"}:
                    self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def error(self, status, detail):
            self.send_bytes(status, json.dumps({"detail": detail}, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def route(self):
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if parsed.scheme or parsed.netloc or "\\" in path or ".." in path.split("/") or "\x00" in path:
                return self.error(400, "请求路径不正确")
            files = native_files()
            # 仅规范化已知页面；保留查询条件和同场练习模式，不吞掉未知路径。
            aliases = {"/" + name: route for route, (name, _) in files.items()
                       if route != "/index.html" and name.endswith(".html")}
            aliases["/index.html"] = "/"
            canonical = path.rstrip("/") or "/"
            canonical = aliases.get(canonical, canonical)
            known_page = canonical in files and files[canonical][0].endswith(".html")
            known_detail = re.fullmatch(r"/(report|interview)/[a-f0-9]{32}", canonical)
            if canonical != path and (known_page or known_detail):
                if self.command not in ("GET", "HEAD"):
                    return self.error(405, "该页面不接受此方法")
                destination = canonical + ("?" + parsed.query if parsed.query else "")
                return self.send_bytes(308, b"", "text/html; charset=utf-8", [("Location", destination)])
            native_detail = re.fullmatch(r"/(report|interview)/[a-f0-9]{32}", path)
            if native_detail:
                files[path] = (native_detail.group(1) + ".html", "text/html; charset=utf-8")
                if native_detail.group(1) == "interview" and parse_qs(parsed.query).get("mode") == ["voice"]:
                    files[path] = ("voice.html", "text/html; charset=utf-8")
                if native_detail.group(1) == "interview" and parse_qs(parsed.query).get("mode") == ["realtime"]:
                    files[path] = ("realtime.html", "text/html; charset=utf-8")
            if path in files:
                if self.command not in ("GET", "HEAD"):
                    return self.error(405, "该页面不接受此方法")
                name, content_type = files[path]
                body = (ROOT / name).read_bytes()
                if name == "index.html":
                    source = body.decode("utf-8")
                    marker = '<body data-api="" data-workspace-base="http://localhost:3000">'
                    if source.count(marker) != 1:
                        return self.error(500, "首页接入标记已变更，请更新联调入口")
                    body = source.replace(marker, '<body data-api="/api" data-workspace-base="">').encode()
                elif name in ('interview.html', 'voice.html', 'realtime.html'):
                    source = body.decode('utf-8')
                    marker = 'data-ws-base=""'
                    if source.count(marker) != 1:
                        return self.error(500, '练习室接入标记已变更')
                    body = source.replace(marker, f'data-ws-base="ws://localhost:{backend_port}"').encode()
                return self.send_bytes(200, body, content_type)
            if path.startswith("/api/"):
                if self.command not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
                    return self.error(405, "接口方法不支持")
                target_port = backend_port
            elif path in ("/legacy-review", "/legacy-account", "/legacy-history", "/legacy-revision", "/workspace") or re.fullmatch(
                    r"/(legacy-interview|legacy-report)/[a-f0-9]{32}", path) or path.startswith("/_next/"):
                if self.command not in ("GET", "HEAD"):
                    return self.error(405, "练习页面仅支持读取")
                target_port = frontend_port
                if path == "/workspace":
                    path = "/"
                elif path == "/legacy-revision":
                    path = "/revision"
                elif path in ("/legacy-account", "/legacy-history", "/legacy-review") or path.startswith(('/legacy-report/', '/legacy-interview/')):
                    path = path.replace('/legacy-', '/')
            else:
                return self.error(404, "页面不存在")
            if self.headers.get("Transfer-Encoding"):
                return self.error(411, "请提供Content-Length")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.error(400, "请求长度不正确")
            if not 0 <= size <= MAX_BODY:
                return self.error(413, "请求内容过大")
            body = self.rfile.read(size) if size else None
            headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_HEADERS}
            headers["Accept-Encoding"] = "identity"
            connection = HTTPConnection("127.0.0.1", target_port, timeout=45)
            try:
                connection.request(self.command, path + ("?" + parsed.query if parsed.query else ""), body=body, headers=headers)
                response = connection.getresponse()
                data = response.read(MAX_RESPONSE + 1)
                if len(data) > MAX_RESPONSE:
                    return self.error(502, "服务响应超过本地联调上限")
                response_headers = []
                for key, value in response.getheaders():
                    if key.lower() == "location":
                        destination = urlsplit(value)
                        if destination.hostname in ("localhost", "127.0.0.1") and destination.port == target_port:
                            value = destination.path + ("?" + destination.query if destination.query else "")
                    response_headers.append((key, value))
                self.send_bytes(response.status, data, response.getheader("Content-Type", "application/octet-stream"), response_headers)
            except (OSError, HTTPException):
                self.error(502, "本地练习服务暂不可用，请稍后重试")
            finally:
                connection.close()

        do_GET = route
        do_HEAD = route
        do_POST = route
        do_PATCH = route
        do_PUT = route
        do_DELETE = route
        do_OPTIONS = route

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
