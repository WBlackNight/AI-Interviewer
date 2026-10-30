"""Loopback-only SMTP sink and test inbox. Never forwards mail or writes files."""
from collections import deque
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import html
import json
import socketserver
import threading

def start_test_mail(smtp_port=1025,http_port=8025):
    inbox=deque(maxlen=20);lock=threading.Lock()
    class SMTP(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(10);self.wfile.write(b'220 localhost test SMTP\r\n')
            for _ in range(100):
                line=self.rfile.readline(4097)
                if not line or len(line)>4096:return
                command=line.split(b' ',1)[0].strip().upper()
                if command in (b'EHLO',b'HELO'):self.wfile.write(b'250 localhost\r\n')
                elif command in (b'MAIL',b'RCPT',b'RSET',b'NOOP'):self.wfile.write(b'250 OK\r\n')
                elif command==b'DATA':
                    self.wfile.write(b'354 End with dot\r\n');raw=bytearray()
                    while True:
                        block=self.rfile.readline(4097)
                        if not block or len(raw)+len(block)>16384:return
                        if block==b'.\r\n':break
                        raw.extend(block[1:] if block.startswith(b'..') else block)
                    message=BytesParser(policy=policy.default).parsebytes(bytes(raw))
                    with lock:inbox.appendleft({'to':str(message.get('To','')),'subject':str(message.get('Subject','')),'body':message.get_content()})
                    self.wfile.write(b'250 Stored locally\r\n')
                elif command==b'QUIT':self.wfile.write(b'221 Bye\r\n');return
                else:self.wfile.write(b'502 Not supported\r\n')
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.headers.get('Host') not in (f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'):
                self.send_error(403);return
            with lock:messages=list(inbox)
            if self.path=='/messages':body=json.dumps(messages,ensure_ascii=False).encode();media='application/json'
            elif self.path=='/':
                cards=''.join('<article><h2>'+html.escape(m['subject'])+'</h2><p>'+html.escape(m['to'])+'</p><pre>'+html.escape(m['body'])+'</pre></article>' for m in messages)
                body=('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>青栈 · 本机测试收件箱</title><style>body{max-width:800px;margin:32px auto;padding:20px;background:#f2f7f3;color:#203c2e;font:16px/1.8 system-ui}article{background:white;padding:24px;border-radius:16px;margin:20px 0}pre{white-space:pre-wrap;font:inherit}a{color:#285841}</style><h1>本机测试收件箱</h1><p>邮件只保留在当前进程内，没有发送到外部邮箱。测试验证码仍按一次性、10分钟有效期校验。</p><a href="/">刷新收件箱</a> · <a href="http://localhost:3000/account">返回账户管理</a>'+ (cards or '<p>暂无邮件，请在账户页获取验证码后刷新。</p>')).encode();media='text/html; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',media);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
    smtp=Server(('127.0.0.1',smtp_port),SMTP)
    try:web=ThreadingHTTPServer(('127.0.0.1',http_port),HTTP)
    except Exception:smtp.server_close();raise
    for server in (smtp,web):threading.Thread(target=server.serve_forever,daemon=True).start()
    return smtp,web
