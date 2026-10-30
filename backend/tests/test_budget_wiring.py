import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from openai import OpenAI
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models.entities import Base, LLMBudgetUsage
from app.llm.budget import use_budget
from app.llm.persistent_budget import PersistentBudget, reconcile
from app.llm.client import OpenAICompatibleLLM
from app.llm.errors import BudgetExceeded
from app.llm.limiter import configure_limit, snapshot
from tests.test_ws_recovery import api, create, connect, answer, receive_turn


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path/'meter.sqlite3').as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    yield factory
    engine.dispose()


def client(outcomes, *, handler=None):
    calls=[]
    def respond(request):
        calls.append(1)
        if handler: return handler(request)
        outcome=outcomes[min(len(calls)-1,len(outcomes)-1)]
        if isinstance(outcome,Exception): raise outcome
        return httpx.Response(200,json=outcome)
    llm=OpenAICompatibleLLM(api_key='synthetic',base_url='https://model.test/v1',model='test',
        max_attempts=2,backoff_base_seconds=.001)
    llm._client.close()
    llm._client=OpenAI(api_key='synthetic',base_url='https://model.test/v1',max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond),trust_env=False))
    return llm,calls


def response(content='{}', usage=True):
    value={'id':'test','created':0,'object':'chat.completion','model':'test',
        'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}]}
    if usage:value['usage']={'prompt_tokens':3,'completion_tokens':2,'total_tokens':5}
    return value


def test_cross_round_and_new_meter_cannot_reset_budget(ledger):
    config=Settings(_env_file=None,llm_budget_tokens_per_interview=8)
    llm,calls=client([response()])
    for _ in range(2):
        with use_budget(PersistentBudget(ledger,'interview','one',config)):
            if len(calls)==0:llm.chat([])
            else:
                with pytest.raises(BudgetExceeded):llm.chat([])
    with use_budget(PersistentBudget(ledger,'interview','one',config)):
        with pytest.raises(BudgetExceeded):llm.chat([])
    assert len(calls)==2
    with ledger() as db:assert db.get(LLMBudgetUsage,('interview','one')).used_tokens==10
    llm.close()


@pytest.mark.parametrize('unknown',[True,False])
def test_missing_usage_or_network_error_blocks_further_budgeted_requests(ledger,unknown):
    config=Settings(_env_file=None,llm_budget_tokens_per_interview=100)
    llm,calls=client([response(usage=False) if unknown else httpx.ReadTimeout('synthetic')])
    with use_budget(PersistentBudget(ledger,'interview','unknown',config)):
        with pytest.raises(BudgetExceeded):llm.chat([])
        with pytest.raises(BudgetExceeded):llm.chat([])
    assert len(calls)==1
    with ledger() as db:
        row=db.get(LLMBudgetUsage,('interview','unknown'))
        assert row.unknown_calls==1 and row.used_tokens==0 and row.pending is None
    llm.close()


def test_empty_response_retries_charge_every_attempt(ledger):
    config=Settings(_env_file=None,llm_budget_tokens_per_interview=100)
    llm,calls=client([response(None),response()])
    with use_budget(PersistentBudget(ledger,'interview','empty',config)):llm.chat([])
    assert len(calls)==2
    with ledger() as db:assert db.get(LLMBudgetUsage,('interview','empty')).used_tokens==10
    llm.close()


def test_crash_pending_persists_and_reconciliation_uses_cas(ledger):
    config=Settings(_env_file=None,llm_budget_tokens_per_interview=100)
    first=PersistentBudget(ledger,'interview','crash',config)
    first.begin_call()  # 模拟发送后进程中止，未结算。
    second=PersistentBudget(ledger,'interview','crash',config)
    with pytest.raises(BudgetExceeded):second.begin_call()
    with ledger() as db:version=db.get(LLMBudgetUsage,('interview','crash')).version
    with pytest.raises(ValueError):reconcile(ledger,'interview','crash',version=version+1,total_tokens=5,total_cost=0)
    reconcile(ledger,'interview','crash',version=version,total_tokens=5,total_cost=0)
    call_id=second.begin_call()
    second.finish_call(call_id,(3,2))
    assert second.used_tokens==10


def test_global_limit_shared_by_distinct_clients():
    configure_limit(1)
    entered,release,second_entered=threading.Event(),threading.Event(),threading.Event()
    def slow(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200,json=response())
    def other(request):
        second_entered.set()
        return httpx.Response(200,json=response())
    first,_=client([],handler=slow)
    second,_=client([],handler=other)
    try:
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(first.chat,[])
            assert entered.wait(2)
            b=pool.submit(second.chat,[])
            assert not second_entered.wait(.1)
            release.set()
            assert a.result(5)=='{}' and b.result(5)=='{}'
        assert snapshot()['active']==0
    finally:
        release.set();configure_limit(4);first.close();second.close()


def test_actual_rest_planner_ws_share_budget_and_duplicate_is_not_billed(api,monkeypatch):
    from app.api import routes,ws
    client_api,factory=api
    config=routes.settings.model_copy(update={'llm_budget_tokens_per_interview':10})
    monkeypatch.setattr(routes,'settings',config);monkeypatch.setattr(ws,'settings',config)
    all_calls=[]
    def build(_):
        model,calls=client([response()]);all_calls.append(calls);return model
    monkeypatch.setattr(routes,'build_llm',build);monkeypatch.setattr(ws,'build_llm',build)
    interview=create(client_api)
    headers={'X-Interview-Token':interview['access_token']}
    path='/api/interview/'+interview['interview_id']+'/usage'
    assert client_api.get(path).status_code==403
    assert client_api.get(path,headers=headers).json()['used_tokens']==5
    with connect(client_api,interview) as (socket,snapshot_value):
        text=('B+树多路叶子链表支持范围查询降低磁盘IO，MVCC通过undo版本链快照实现隔离。'
              '线程池核心线程队列最大线程拒绝策略。JVM堆栈方法区程序计数器线程私有共享OOM GC垃圾回收。'
              'Redis缓存穿透布隆过滤器热点击穿互斥锁雪崩随机过期，实际项目实践。')
        payload=answer(snapshot_value,text=text)
        socket.send_json(payload)
        events=receive_turn(socket)
        assert any(e['type']=='score' for e in events),events
        socket.send_json(payload)
        assert receive_turn(socket)==events
        question=next(e for e in events if e['type']=='question')
        socket.send_json(dict(payload,message_id='blocked',turn_id=question['turn_id'],version=question['version']))
        assert socket.receive_json()['code']=='llm_budget_blocked'
    assert sum(map(len,all_calls))==2
    assert client_api.get(path,headers=headers).json()['used_tokens']==10


def test_resume_budget_scope_is_authorized_and_durable(api,monkeypatch):
    from app.api import routes
    client_api,_=api
    model,calls=client([response()])
    monkeypatch.setattr(routes,'build_llm',lambda _:model)
    result=client_api.post('/api/resume',json={'resume_text':'专业技能\nJava'}).json()
    path='/api/resume/'+result['resume_id']+'/usage'
    assert client_api.get(path).status_code==403
    assert client_api.get(path,headers={'X-Resume-Token':result['access_token']}).json()['used_tokens']==5


def test_invalid_money_configuration_rejected():
    with pytest.raises(ValueError):Settings(_env_file=None,llm_budget_cost_per_interview=1)
    with pytest.raises(ValueError):Settings(_env_file=None,llm_price_input_per_million=float('nan'))


def test_budget_survives_real_interpreter_restart(ledger):
    import subprocess,sys
    from pathlib import Path
    config=Settings(_env_file=None,llm_budget_tokens_per_interview=100)
    meter=PersistentBudget(ledger,'interview','restart',config)
    meter.finish_call(meter.begin_call(),(3,2))
    url=str(ledger.kw['bind'].url)
    code=("from sqlalchemy import create_engine; from sqlalchemy.orm import sessionmaker; "
          "from app.config import Settings; from app.llm.persistent_budget import PersistentBudget; "
          f"f=sessionmaker(create_engine({url!r})); "
          "print(PersistentBudget(f,'interview','restart',Settings(_env_file=None,llm_budget_tokens_per_interview=100)).used_tokens)")
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],
                          capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='5'


def test_money_and_frozen_policy_cannot_be_reset(ledger):
    config=Settings(_env_file=None,llm_budget_cost_per_interview=.000004,
        llm_price_input_per_million=1,llm_price_output_per_million=1)
    meter=PersistentBudget(ledger,'interview','money',config)
    with pytest.raises(BudgetExceeded):meter.finish_call(meter.begin_call(),(3,2))
    newer=PersistentBudget(ledger,'interview','money',config.model_copy(update={'llm_budget_cost_per_interview':100}))
    with pytest.raises(BudgetExceeded):newer.begin_call()


def test_independent_bill_survives_business_rollback(ledger):
    from app.models.entities import User
    config=Settings(_env_file=None)
    meter=PersistentBudget(ledger,'interview','rollback',config)
    meter.finish_call(meter.begin_call(),(3,2))
    with ledger() as db:
        db.add(User(name='synthetic'))
        db.flush();db.rollback()
    assert PersistentBudget(ledger,'interview','rollback',config).used_tokens==5


def test_settlement_write_failure_is_not_heuristic_fallback():
    class Broken:
        def begin_call(self):return 'pending'
        def finish_call(self,*args):raise OSError('synthetic database error')
    model,calls=client([response()])
    with use_budget(Broken()):
        with pytest.raises(BudgetExceeded):model.chat([])
    assert len(calls)==1
    model.close()
