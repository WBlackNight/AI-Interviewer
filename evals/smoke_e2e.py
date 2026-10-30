"""真实 HTTP/WS 文字面试冒烟，可自启独立服务并验证进程重启恢复。

python evals/smoke_e2e.py                         # 已有服务 8200
python evals/smoke_e2e.py --start-server --restart # 隔离数据库与自动清理
python evals/smoke_e2e.py --start-server --restart --pdf # 合成PDF上传后完成面试
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import signal

import websockets

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RESUME = '教育经历\n示例大学 计算机科学\n专业技能\nJava、Spring、MySQL、Redis、并发编程、JVM\n项目经历\n示例电商系统'
ANSWER = ('B+树是多路平衡搜索树，支持范围查询，叶子链表降低磁盘IO。'
          'MVCC通过undo版本链与快照实现隔离。线程池核心线程、队列、最大线程、拒绝策略。'
          'JVM运行时数据区包括堆、虚拟机栈、方法区、程序计数器，区分线程私有与共享，'
          'OOM内存溢出需要GC垃圾回收。Redis缓存穿透使用布隆过滤器，热点击穿用互斥锁，'
          '雪崩时随机过期，我们实际项目做过方案优化。')
CODE = '''def two_sum(nums, target):
    seen = {}
    for i, value in enumerate(nums):
        if target - value in seen:
            return [seen[target - value], i]
        seen[value] = i
    return []
import sys
nums = list(map(int, sys.stdin.readline().split()))
target = int(sys.stdin.readline())
print(two_sum(nums, target))'''


def request(base, path, payload=None, headers=None):
    if path=='/api/auth/register' and payload is not None:
        captcha=request(base,'/api/auth/captcha')
        payload={**payload,'password_confirm':payload['password'],'captcha_id':captcha['captcha_id'],'captcha_code':'TEST2'}
    headers = {'Content-Type': 'application/json', **(headers or {})}
    req = urllib.request.Request(base + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
        method='POST' if payload is not None else 'GET')
    with OPENER.open(req, timeout=30) as response:
        return json.loads(response.read())


class Server:
    def __init__(self, db_path, *, retrieval_provider='bm25', index_path=None, dimensions=256,
                 embedding_provider='hash', use_llm=False, allow_llm_fallback=False,
                 bank_dir=None, skill_tree_dir=None, voice_provider='disabled', test_captcha=True):
        assert db_path.resolve().is_relative_to(BACKEND.resolve())
        self.db_path = db_path
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        self.base = f'http://127.0.0.1:{self.port}'
        self.process = None
        self.pid_file = db_path.with_suffix('.pid')
        self.retrieval_provider = retrieval_provider
        self.index_path = index_path or ROOT / 'data/retrieval/question_index.json'
        self.dimensions = dimensions
        self.embedding_provider = embedding_provider
        self.use_llm = use_llm
        self.allow_llm_fallback = allow_llm_fallback
        self.bank_dir = Path(bank_dir or ROOT / 'data/question_bank').resolve()
        self.skill_tree_dir = Path(skill_tree_dir or ROOT / 'data/skill_tree').resolve()
        self.voice_provider = voice_provider
        self.test_captcha = test_captcha

    def start(self):
        env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + self.db_path.as_posix(),
               'JUDGE0_URL': '', 'VOICE_ENABLED': 'false', 'PYTHONUTF8': '1',
               'RETRIEVAL_PROVIDER': self.retrieval_provider,
               'QUESTION_BANK_DIR': str(self.bank_dir), 'SKILL_TREE_DIR': str(self.skill_tree_dir),
               'RETRIEVAL_INDEX_PATH': str(self.index_path.resolve()),
               'EMBEDDING_PROVIDER': self.embedding_provider,
               'EMBEDDING_MODEL': 'embedding-3' if self.embedding_provider == 'zhipu' else 'char-ngram-hash-v1',
               'EMBEDDING_DIMENSIONS': str(self.dimensions)}
        if self.voice_provider in ('dummy', 'doubao'):
            env.update(VOICE_ENABLED='true', VOICE_ASR_PROVIDER=self.voice_provider,
                       VOICE_TTS_PROVIDER=self.voice_provider,
                       VOICE_ASR_DUMMY_TEXT='这是用于协议验收的预设转写，不是真实识别结果。')
        if self.use_llm:
            # 密钥由backend/.env或服务端环境读取；显式远程模式使用有界合成面试。
            env.update(LLM_STRICT_MODE='false' if self.allow_llm_fallback else 'true', SCORING_CACHE_ENABLED='false',
                       MAX_PLAN_THEMES='1', PROBE_DEPTH_LIMIT='1', LLM_MAX_ATTEMPTS='1')
        else:
            env['LLM_API_KEY'] = ''
        self.pid_file.unlink(missing_ok=True)
        # Windows venv 启动器可能再创建解释器子进程，记录真正服务进程的 PID。
        bootstrap = ("import os; from pathlib import Path; "
            f"Path({str(self.pid_file)!r}).write_text(str(os.getpid())); "
            "import uvicorn; "
            f"uvicorn.run('app.main:app', host='127.0.0.1', port={self.port})")
        if self.test_captcha:
            bootstrap=bootstrap.replace('import uvicorn;', "import app.services.account_security as cap; cap.generate_code=lambda:'TEST2'; import uvicorn;")
        self.process = subprocess.Popen([sys.executable, '-c', bootstrap], cwd=BACKEND, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('临时后端启动失败')
            try:
                health = request(self.base, '/api/health')
                if self.pid_file.exists() and health.get('process_id') == int(self.pid_file.read_text()):
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError('临时后端启动超时')

    def stop(self):
        if self.process is not None:
            if self.pid_file.exists():
                try:
                    os.kill(int(self.pid_file.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

    def restart(self):
        self.stop()
        self.start()


def create_pdf_resume(base):
    """带文本层的合成PDF，经真实HTTP上传；不读用户文件。"""
    import io
    import httpx
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
        DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 50 790 Td 16 TL (skills) Tj T* '
        b'(Java Spring MySQL Redis JVM) Tj T* (projects) Tj T* '
        b'(Synthetic cache project 13812345678 synthetic@example.com) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    with httpx.Client(trust_env=False, timeout=30) as client:
        response = client.post(base + '/api/resume/pdf',
            files={'file': ('synthetic.pdf', buffer.getvalue(), 'application/pdf')},
            data={'name': 'Synthetic User'})
        response.raise_for_status()
        result = response.json()
    assert '13812345678' not in response.text and 'synthetic@example.com' not in response.text
    assert any(re.search(r'(?i)(?<![a-z])java(?![a-z])', skill) for skill in result['skills'])
    assert len(result['access_token']) == 64
    return result


async def run(base, restart=None, *, use_pdf=False, retrieval_provider='bm25', embedding_provider='hash',
              use_llm=False, json_out=None, allow_llm_fallback=False, position='java_backend'):
    health = request(base, '/api/health')
    assert health['status'] == 'ok'
    if use_llm:
        assert health['llm_enabled'], '真实LLM模式需要配置服务端密钥'
    retrieval = request(base, '/api/diagnostics/retrieval')
    assert retrieval['requested'] == retrieval_provider, retrieval
    if retrieval_provider != 'bm25':
        assert retrieval['index_state'] == 'ready', retrieval
        assert retrieval['embedding']['provider'] == embedding_provider, retrieval
    retrieval_snapshots = []
    llm_snapshots = []
    resume = create_pdf_resume(base) if use_pdf else request(base, '/api/resume',
        {'name': '示例用户', 'resume_text': RESUME})
    created = request(base, '/api/interview', {'resume_id': resume['resume_id'],
        'position': position, 'difficulty': 'mid'}, {'X-Resume-Token': resume['access_token']})
    assert abs(sum(p['weight'] for p in created['plan']) - 1) < .001
    interview_id, token = created['interview_id'], created['access_token']
    usage_headers = {'X-Interview-Token': token}
    created_summary = request(base, f'/api/interview/{interview_id}', headers=usage_headers)
    assert created_summary['status'] == 'created' and created_summary['answer_count'] == 0
    usage_before_restart = None
    url = base.replace('http', 'ws', 1) + f'/ws/interview/{interview_id}'
    protocols = ['interview', token]
    answered = 0
    complete = False
    restarted = False
    pending = None
    expected = None
    # 每轮重新连接，同时覆盖断线补发、幂等重试和全历史恢复。
    for _ in range(50):
        async with websockets.connect(url, subprotocols=protocols) as ws:
            await ws.send(json.dumps({'type': 'start'}))
            state = json.loads(await asyncio.wait_for(ws.recv(), 90 if use_llm else 30))
            assert state['type'] == 'snapshot', state
            events = state['events']
            seqs = [e['seq'] for e in events]
            assert seqs == list(range(len(seqs))), seqs
            if expected:
                assert state['current_question'] == expected
            if pending:
                # 重发上一轮完全相同的 message_id，返回原事件且不重复推进。
                usage_before_replay = request(base, f'/api/interview/{interview_id}/usage',
                                             headers=usage_headers) if use_llm else None
                await ws.send(json.dumps(pending))
                while True:
                    old = json.loads(await asyncio.wait_for(ws.recv(), 90 if use_llm else 30))
                    assert old['type'] != 'error', old
                    if old['type'] in ('question', 'report_ready'):
                        break
                if use_llm:
                    usage_after_replay = request(base, f'/api/interview/{interview_id}/usage', headers=usage_headers)
                    assert usage_after_replay['used_tokens'] == usage_before_replay['used_tokens']
                    assert usage_after_replay['version'] == usage_before_replay['version']
                pending = None
            if state['finished']:
                complete = True
                assert sum(e['type'] == 'score' for e in events) == answered
                break
            question = state['current_question']
            assert question and question['turn_id']
            assert question['id'].startswith('py-' if position == 'python_backend' else 'jv-'), question
            text = '我只知道索引有助于加速查询，具体结构还不清楚。' if use_llm and answered == 0 else (
                '默认参数在定义时创建，共享可变对象会保留修改，应使用None哨兵在函数内创建列表。'
                '生成器使用yield暂停保存状态，迭代到耗尽抛StopIteration，惰性处理节省内存，with关闭资源。'
                '事件循环线程不应阻塞，await异步客户端，必要时to_thread并设置超时。'
                'CancelledError协作传播，finally清理，线程中的同步调用不会自动终止，用版本标识丢弃过期迟到结果。'
                '参数绑定分离SQL结构和数据避免注入，动态表名排序使用白名单。'
                '事务中原子提交失败回滚，避免长期持锁调用外部服务，外部副作用不会撤销，需要幂等补偿outbox。'
                if position == 'python_backend' else ANSWER)
            pending = {'type': 'answer', 'message_id': uuid.uuid4().hex,
                'turn_id': question['turn_id'], 'version': state['version'], 'text': text}
            if question.get('is_coding'):
                pending['code'] = CODE
            await ws.send(json.dumps(pending))
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 90 if use_llm else 30))
                assert event['type'] != 'error', event
                if event['type'] == 'score':
                    assert event['question_id'] == question['id']
                    assert event['turn_id'] == question['turn_id']
                    answered += 1
                if event['type'] == 'question':
                    expected = event
                    break
                if event['type'] == 'report_ready':
                    expected = None
                    break
        if restart and not restarted:
            retrieval_snapshots.append(request(base, '/api/diagnostics/retrieval'))
            if use_llm:
                llm_snapshots.append(request(base, '/api/diagnostics/llm'))
                usage_before_restart = request(base, f'/api/interview/{interview_id}/usage', headers=usage_headers)
            await asyncio.to_thread(restart)
            restarted = True
            if use_llm:
                restored_usage = request(base, f'/api/interview/{interview_id}/usage', headers=usage_headers)
                assert restored_usage['used_tokens'] == usage_before_restart['used_tokens']
                assert restored_usage['version'] == usage_before_restart['version']
            print('已重启后端：将从同一数据库恢复当前题，并重试上一轮消息')
    assert complete, '面试未完成'
    report = request(base, f'/api/interview/{interview_id}/report',
                     headers={'X-Interview-Token': token})
    assert report['is_complete'] and report['answer_count'] == answered
    assert report['overall'] > 0 and report['question_count'] <= answered
    assert len(report['per_question']) == answered
    history_summary = request(base, f'/api/interview/{interview_id}', headers=usage_headers)
    assert history_summary['status'] == 'finished' and history_summary['answer_count'] == answered
    # 两种附件均走真实HTTP；不读取浏览器凭据，不调用额外模型。
    for export_format in ('markdown', 'json'):
        download = urllib.request.Request(base + f'/api/interview/{interview_id}/report/export?format={export_format}',
                                          headers=usage_headers)
        with OPENER.open(download, timeout=30) as response:
            body = response.read().decode('utf-8')
            assert response.headers['Cache-Control'] == 'no-store'
            assert 'attachment;' in response.headers['Content-Disposition']
        assert token not in body
        if export_format == 'json':
            assert json.loads(body) == report
        else:
            assert '面试复盘报告' in body and all(q['answer_text'] in body for q in report['per_question'])
    retrieval = request(base, '/api/diagnostics/retrieval')
    retrieval_snapshots.append(retrieval)
    fallbacks = sum(row.get('counts', {}).get('fallback', 0) for row in retrieval_snapshots)
    if retrieval_provider != 'bm25':
        assert sum(row.get('counts', {}).get('success', 0) for row in retrieval_snapshots) > 0, retrieval
        assert fallbacks == 0, retrieval_snapshots
    usage = {key: sum(row.get('embedding_usage', {}).get(key, 0) for row in retrieval_snapshots)
             for key in ('network_calls', 'provider_reported_tokens', 'unknown_usage_calls')}
    llm_result = None
    if use_llm:
        llm_snapshots.append(request(base, '/api/diagnostics/llm'))
        totals = {name: {key: sum(row['components'].get(name, {}).get(key, 0) for row in llm_snapshots)
                        for key in ('calls', 'llm_success', 'heuristic_fallback', 'error_raised')}
                  for name in ('resume_parser', 'planner', 'scorer', 'prober')}
        for name, counts in totals.items():
            assert counts['calls'] > 0 and counts['error_raised'] == 0, (name, counts)
            if not allow_llm_fallback:
                assert counts['llm_success'] == counts['calls'] and counts['heuristic_fallback'] == 0, (name, counts)
        interview_usage = request(base, f'/api/interview/{interview_id}/usage', headers=usage_headers)
        resume_usage = request(base, f"/api/resume/{resume['resume_id']}/usage",
                               headers={'X-Resume-Token': resume['access_token']})
        for meter in (interview_usage, resume_usage):
            assert meter['used_tokens'] > 0 and not meter['pending'] and meter['unknown_calls'] == 0, meter
        llm_result = {'model': llm_snapshots[-1]['model'], 'components': totals,
                      'diagnostic_snapshots': llm_snapshots,
                      'all_llm_success': all(c['llm_success'] == c['calls'] for c in totals.values()),
                      'allow_llm_fallback': allow_llm_fallback,
                      'interview_usage': interview_usage, 'resume_usage': resume_usage,
                      'usage_before_restart': usage_before_restart, 'synthetic_inputs_only': True}
    summary = {'result': 'passed', 'position': position, 'questions': report['question_count'],
        'answers': answered, 'overall': report['overall'], 'restart_verified': restarted,
        'reconnect_and_idempotency': True, 'resume_source': 'pdf' if use_pdf else 'text',
        'retrieval_provider': retrieval_provider, 'retrieval_fallbacks': fallbacks,
        'embedding_provider': embedding_provider, 'embedding_usage': usage, 'llm': llm_result,
        'history_summary_verified': True, 'report_exports_verified': ['markdown', 'json']}
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8200')
    parser.add_argument('--start-server', action='store_true')
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--pdf', action='store_true', help='上传合成PDF简历后走完整面试')
    parser.add_argument('--retrieval', choices=['bm25', 'vector', 'hybrid'], default='bm25')
    parser.add_argument('--position', choices=['java_backend', 'python_backend'], default='java_backend')
    parser.add_argument('--index-path', type=Path, default=ROOT / 'data/retrieval/question_index.json')
    parser.add_argument('--dimensions', type=int, default=256)
    parser.add_argument('--embedding-provider', choices=['hash', 'zhipu'], default='hash',
                        help='zhipu显式调用远程API；密钥只从服务端环境或.env读取')
    parser.add_argument('--llm', action='store_true', help='显式调用真实LLM，严格校验四组件与用量恢复')
    parser.add_argument('--allow-llm-fallback', action='store_true',
                        help='仅验证真实LLM故障回退后的流程，不作为四组件全成功验收')
    parser.add_argument('--json-out', type=Path)
    parser.add_argument('--asset-release', type=Path, help='先校验成套资产，再显式用于隔离服务')
    parser.add_argument('--asset-variant', choices=['baseline', 'candidate'], default='candidate')
    args = parser.parse_args()
    if args.allow_llm_fallback and not args.llm:
        parser.error('--allow-llm-fallback需要--llm')
    if args.restart and not args.start_server:
        parser.error('--restart 需要 --start-server，以免重启用户已有服务')
    bank_dir, skill_tree_dir = None, None
    if args.asset_release:
        if not args.start_server or args.embedding_provider != 'hash':
            parser.error('--asset-release仅用于--start-server与包内hash离线索引')
        if args.json_out and args.json_out.resolve().is_relative_to(args.asset_release.resolve()):
            parser.error('--json-out不得写入成套资产目录')
        sys.path.insert(0, str(BACKEND))
        from app.services.question_release import verify_release
        try:
            verify_release(args.asset_release)
        except Exception:
            failure = {'result': 'failed', 'error_category': 'asset_release_invalid'}
            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_bytes((json.dumps(failure) + '\n').encode('utf-8'))
            print(json.dumps(failure))
            return 1
        stage = args.asset_release.resolve() / args.asset_variant
        bank_dir, skill_tree_dir = stage / 'question_bank', stage / 'skill_tree'
        args.index_path, args.dimensions = stage / 'retrieval/hash-256.json', 256
    if not args.start_server:
        return asyncio.run(run(args.base_url.rstrip('/'), use_pdf=args.pdf, retrieval_provider=args.retrieval,
                               embedding_provider=args.embedding_provider, use_llm=args.llm, json_out=args.json_out,
                               allow_llm_fallback=args.allow_llm_fallback, position=args.position))
    with tempfile.TemporaryDirectory(prefix='.smoke-', dir=BACKEND) as directory:
        task_dir = Path(directory).resolve()
        assert task_dir.is_relative_to(BACKEND.resolve())
        server = Server(task_dir / 'smoke.sqlite3', retrieval_provider=args.retrieval,
                        index_path=args.index_path, dimensions=args.dimensions,
                        embedding_provider=args.embedding_provider, use_llm=args.llm,
                        allow_llm_fallback=args.allow_llm_fallback,
                        bank_dir=bank_dir, skill_tree_dir=skill_tree_dir)
        try:
            server.start()
            return asyncio.run(run(server.base, server.restart if args.restart else None,
                                   use_pdf=args.pdf, retrieval_provider=args.retrieval,
                                   embedding_provider=args.embedding_provider, use_llm=args.llm, json_out=args.json_out,
                                   allow_llm_fallback=args.allow_llm_fallback, position=args.position))
        except Exception as exc:
            failed = {'result': 'failed', 'error_category': type(exc).__name__}
            status = getattr(getattr(exc, 'response', None), 'status_code', getattr(exc, 'code', None))
            if isinstance(status, int) and 100 <= status <= 599:
                failed['http_status'] = status
            if server.process is not None and server.process.poll() is None:
                try:
                    failed['llm_diagnostics'] = request(server.base, '/api/diagnostics/llm')
                    failed['retrieval_diagnostics'] = request(server.base, '/api/diagnostics/retrieval')
                    import sqlite3
                    from contextlib import closing
                    with closing(sqlite3.connect(server.db_path)) as database:
                        rows = database.execute('SELECT used_tokens, unknown_calls, pending FROM llm_budget_usage').fetchall()
                        failed['budget_totals'] = {'used_tokens': sum(row[0] for row in rows),
                            'unknown_calls': sum(row[1] for row in rows), 'pending': sum(bool(row[2]) for row in rows)}
                except Exception:
                    failed['diagnostics_unavailable'] = True
            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(json.dumps(failed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(failed, ensure_ascii=False))
            return 1
        finally:
            server.stop()
            # TemporaryDirectory 只清理已验证属于 backend 的本次临时路径。


if __name__ == '__main__':
    sys.exit(main())
