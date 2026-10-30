import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app.config import Settings
from app.domain import TestCase as Case
from app.sandbox.admission import Admission, AdmissionError, admission
from app.sandbox.judge0 import Judge0Sandbox, SandboxUnavailable
from tests.test_sandbox_report import sandbox
from tests.test_ws_recovery import api


def test_shared_admission_bounds_queue_and_releases_on_exception():
    gate=Admission(1,0)
    with pytest.raises(RuntimeError):
        with gate.slot(.1):
            with pytest.raises(AdmissionError,match='queue_full'):
                with gate.slot(.1):pass
            raise RuntimeError('synthetic')
    assert gate.snapshot()['active']==0


def test_wait_timeout_does_not_leak_ticket():
    gate=Admission(1,1)
    with gate.slot(.1):
        with pytest.raises(AdmissionError,match='queue_timeout'):
            with gate.slot(.01):pass
    assert gate.snapshot()['waiting']==gate.snapshot()['active']==0


def test_admission_waiter_runs_after_release():
    gate=Admission(1,1);entered=threading.Event()
    def waiter():
        with gate.slot(2):entered.set()
    with ThreadPoolExecutor(1) as pool:
        with gate.slot(.1):
            future=pool.submit(waiter)
            assert not entered.wait(.05)
        future.result(2)
    assert entered.is_set() and gate.snapshot()['active']==0


@pytest.mark.parametrize('status',range(3,13))
def test_all_candidate_terminal_statuses(monkeypatch,status):
    judge,_=sandbox(monkeypatch,[status])
    result=judge.judge('print(1)',[Case('','1')])
    assert result.passed==int(status==3) and result.detail[0]['status_id']==status


@pytest.mark.parametrize('status,code,retryable',[(429,'rate_limited',True),(401,'configuration',False),(422,'configuration',False),(503,'transport',True)])
def test_http_failures_have_fixed_codes(monkeypatch,status,code,retryable):
    original=httpx.Client
    monkeypatch.setattr('app.sandbox.judge0.httpx.Client',lambda **kw:original(
        transport=httpx.MockTransport(lambda request:httpx.Response(status,json={'secret':'private'})),**kw))
    with pytest.raises(SandboxUnavailable) as exc:Judge0Sandbox('http://mock').judge('x',[Case('','')])
    assert exc.value.code==code and exc.value.retryable is retryable and 'private' not in str(exc.value)


@pytest.mark.parametrize('body',[b'x'*2048,b'null',b'{invalid',b'{"token":"../private"}'])
def test_oversized_or_invalid_response_never_returns_score(monkeypatch,body):
    original=httpx.Client
    monkeypatch.setattr('app.sandbox.judge0.httpx.Client',lambda **kw:original(
        transport=httpx.MockTransport(lambda request:httpx.Response(200,content=body)),**kw))
    with pytest.raises(SandboxUnavailable):Judge0Sandbox('http://mock',max_response_bytes=1024).judge('x',[Case('','')])
    assert admission.snapshot()['active']==0


def test_case_limits_before_network(monkeypatch):
    def forbidden(**kw):raise AssertionError('must not access network')
    monkeypatch.setattr('app.sandbox.judge0.httpx.Client',forbidden)
    judge=Judge0Sandbox('http://mock',max_testcases=1)
    with pytest.raises(ValueError):judge.judge('x',[Case('','')]*2)
    with pytest.raises(ValueError):judge.judge('x',[Case('x'*65537,'')])


def test_queue_full_makes_no_external_request(monkeypatch):
    admission.configure(1,0)
    try:
        with admission.slot(.1):
            with pytest.raises(SandboxUnavailable,match='queue_full'):
                Judge0Sandbox('http://127.0.0.1:9').judge('x',[Case('','')])
    finally:admission.configure(2,8)


def test_diagnostics_does_not_claim_execution(api):
    client,_=api
    value=client.get('/api/diagnostics/sandbox').json()
    assert value['execution_verified'] is False and value['admission']['scope']=='process'


def test_unconfigured_probe_is_not_success():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from evals.sandbox_probe import probe
    result,code=probe(Settings(_env_file=None,judge0_url=None))
    assert code==2 and not result['execution_verified']


def test_ws_sandbox_failure_preserves_turn_and_retry_can_commit(api,monkeypatch):
    from app.api import ws
    from app.domain import SandboxResult
    from tests.test_ws_recovery import create,connect,answer,receive_turn
    client,_=api
    class Service:
        fail=True
        def judge(self,code,cases):
            if self.fail:raise SandboxUnavailable('queue_full')
            return SandboxResult(len(cases),len(cases),[])
    service=Service()
    monkeypatch.setattr(ws,'build_sandbox',lambda _:service)
    interview=create(client)
    text=('B+树多路叶子链表范围查询降低磁盘IO，MVCC undo版本链快照隔离。'
          '线程池核心线程队列最大线程拒绝策略。JVM堆栈方法区程序计数器线程私有共享OOM GC垃圾回收。'
          'Redis缓存穿透布隆过滤器热点击穿互斥锁雪崩随机过期实际项目。')
    with connect(client,interview) as (socket,snapshot):
        current=snapshot
        for _ in range(10):
            if current['current_question']['is_coding']:break
            socket.send_json(answer(current,text=text))
            events=receive_turn(socket)
            question=next(e for e in events if e['type']=='question')
            current={'current_question':question,'version':question['version']}
        assert current['current_question']['is_coding']
        payload=answer(current,text='数组算法',code='print([])')
        socket.send_json(payload)
        error=socket.receive_json()
        assert error['code']=='sandbox_queue_full' and error['retryable']
        socket.send_json({'type':'start'})
        restored=socket.receive_json()
        assert restored['version']==current['version']
        assert restored['current_question']['turn_id']==current['current_question']['turn_id']
        count=sum(e['type']=='score' for e in restored['events'])
        service.fail=False
        socket.send_json(payload)
        events=receive_turn(socket)
        assert any(e['type']=='score' for e in events)
        socket.send_json({'type':'start'})
        assert sum(e['type']=='score' for e in socket.receive_json()['events'])==count+1


@pytest.mark.parametrize('execute,allow_network,expected_code',[(False,False,0),(True,False,0),(True,True,1)])
def test_probe_defaults_read_only_and_rejects_unsafe_config(monkeypatch,execute,allow_network,expected_code):
    import base64,json,sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from evals.sandbox_probe import probe
    original=httpx.Client
    requests=[];terminal=[3]
    def respond(request):
        requests.append(request)
        if request.url.path=='/config_info':
            return httpx.Response(200,json={'enable_network':False,'allow_enable_network':allow_network})
        if request.url.path.startswith('/languages/'):
            return httpx.Response(200,json={'name':'Python 3'})
        if request.method=='POST':
            code=base64.b64decode(json.loads(request.content)['source_code']).decode()
            terminal[0]=5 if 'while True' in code else 6 if 'def broken' in code else 4 if 'print(0)' in code else 3
            return httpx.Response(201,json={'token':'synthetic-token'})
        return httpx.Response(200,json={'status':{'id':terminal[0]},'stdout':''})
    monkeypatch.setattr('httpx.Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    result,exit_code=probe(Settings(_env_file=None,judge0_url='http://mock'),execute)
    assert exit_code==expected_code and result['isolation_verified'] is False
    assert sum(r.method=='POST' for r in requests)==(4 if execute and not allow_network else 0)
    assert result['execution_verified']==(execute and not allow_network)
