"""真实联调工具与HTTP协议的离线故障注入；不读取或使用真实密钥。"""
import json
from pathlib import Path
import sys

import httpx
import pytest
from openai import OpenAI

from app.config import Settings
from app.llm.client import OpenAICompatibleLLM
from app.llm.errors import LLMError, as_llm_error
from app.llm.resilience import configure_strict, strict_enabled
from app.rag.question_bank import QuestionBank

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals import llm_ping


def response(content="{}", *, finish="stop", usage=True):
    data = {"id": "synthetic", "object": "chat.completion", "created": 0, "model": "synthetic",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": finish}]}
    if usage:
        data["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    return httpx.Response(200, json=data)


def client(handler, **kwargs):
    llm = OpenAICompatibleLLM(api_key="synthetic", base_url="https://model.test/v1", model="synthetic",
                              max_attempts=1, **kwargs)
    llm._client.close()
    llm._client = OpenAI(api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False))
    return llm


@pytest.mark.parametrize("thinking", [None, "disabled", "enabled"])
def test_output_limit_and_optional_thinking_reach_wire(thinking):
    def handler(request):
        body = json.loads(request.content)
        assert body["max_tokens"] == 1024 and body["response_format"] == {"type": "json_object"}
        if thinking is None:
            assert "thinking" not in body
        else:
            assert body["thinking"] == {"type": thinking}
        return response()
    llm = client(handler, max_output_tokens=1024, thinking_mode=thinking)
    try:
        assert llm.chat([{"role": "user", "content": "JSON"}], json_mode=True) == "{}"
        assert llm.usage_diagnostics()["network_calls"] == 1
        assert llm.usage_diagnostics()["unknown_usage_calls"] == 0
    finally:
        llm.close()


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_nonterminal_or_truncated_output_rejected_but_usage_counted(finish):
    llm = client(lambda req: response(finish=finish))
    try:
        with pytest.raises(LLMError): llm.chat([])
        assert llm.usage == {"tokens_in": 10, "tokens_out": 5}
        assert llm.usage_diagnostics()["network_calls"] == 1
    finally:
        llm.close()


def test_exception_body_not_in_logs_or_error(caplog):
    private = "synthetic-secret email@example.com"
    error = as_llm_error(ValueError(private))
    assert private not in str(error) + error.detail
    llm = client(lambda req: httpx.Response(401, json={"error": {"message": private}}))
    try:
        with pytest.raises(LLMError) as caught: llm.chat([])
        assert private not in str(caught.value) + caplog.text
        assert llm.usage_diagnostics()["unknown_usage_calls"] == 1
    finally:
        llm.close()


def test_fixed_validation_reason_drops_dynamic_content():
    error = as_llm_error(ValueError('评分引用不属于原回答 synthetic-secret'))
    assert error.detail == 'quote_not_in_answer'
    assert 'synthetic-secret' not in str(error)


def test_telemetry_counts_only_fixed_validation_reasons(caplog):
    from app.llm.errors import LLMErrorKind
    from app.llm.telemetry import CallOutcome, LLMTelemetry

    telemetry = LLMTelemetry()
    for reason in ("quote_not_in_answer", "synthetic-secret email@example.com"):
        telemetry.record("scorer", CallOutcome.ERROR_RAISED,
                         error_kind=LLMErrorKind.BAD_PAYLOAD, detail=reason)
    stats = telemetry.snapshot()["scorer"]
    assert stats["error_kinds"] == {"bad_payload": 2}
    assert stats["validation_reasons"] == {"quote_not_in_answer": 1}
    assert "synthetic-secret" not in caplog.text + json.dumps(stats)


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limit"), (503, "server")])
@pytest.mark.parametrize("entry", ["primary", "handler"])
def test_unknown_usage_pause_preserves_provider_category(monkeypatch, caplog, status, kind, entry):
    from app.llm.budget import TokenBudget, use_budget
    from app.llm.errors import BudgetExceeded, classify_exception
    from app.llm import resilience
    from app.llm.telemetry import LLMTelemetry

    telemetry = LLMTelemetry()
    monkeypatch.setattr(resilience, "get_telemetry", lambda: telemetry)
    llm = client(lambda req: httpx.Response(status, json={"error": {"message": "private-provider-body"}}))
    def blocked_fallback():
        pytest.fail("未知用量暂停不能回退")
    def invoke():
        if entry == "primary":
            return resilience.call_with_fallback(component="scorer", primary=lambda: llm.chat([]),
                                                 fallback=blocked_fallback)
        try:
            llm.chat([])
        except Exception as exc:
            return resilience.handle_fallback(component="scorer", exc=exc, fallback=blocked_fallback)
    try:
        with use_budget(TokenBudget(limit_tokens=10000)), pytest.raises(BudgetExceeded) as caught:
            invoke()
        assert caught.value.provider_kind.value == kind
        assert classify_exception(caught.value).value == "budget_exceeded"
        stats = telemetry.snapshot()["scorer"]
        assert stats["error_raised"] == 1 and stats["heuristic_fallback"] == 0
        assert stats["error_kinds"] == {kind: 1}
        assert llm.usage_diagnostics()["network_calls"] == llm.usage_diagnostics()["unknown_usage_calls"] == 1
        assert "private-provider-body" not in str(caught.value) + caplog.text
    finally:
        llm.close()


@pytest.mark.parametrize("kwargs", [{"llm_max_output_tokens": 0}, {"llm_max_output_tokens": 9000},
                                    {"llm_thinking_mode": "invalid"}])
def test_invalid_request_configuration(kwargs):
    with pytest.raises(ValueError): Settings(_env_file=None, **kwargs)


@pytest.fixture
def probe(monkeypatch):
    config = Settings(_env_file=None, llm_api_key="synthetic", scoring_cache_enabled=True)
    question = QuestionBank.load(config.question_bank_dir).get('jv-mysql-index-001')
    count = {name: 0 for name in llm_ping.COMPONENTS}
    faults = {}
    def handler(request):
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "从简历抽取" in prompt:
            component = "resume_parser"
            data = {"skills": ["Java", "MySQL"], "projects": [], "education": ""}
        elif "面试官教练" in prompt:
            component = "planner"
            constraints = json.loads(body["messages"][1]["content"])
            assert "MySQL" in [item["theme"] for item in constraints["allowed_themes"]]
            assert "Java" not in [item["theme"] for item in constraints["allowed_themes"]]
            data = {"plan": [{"theme": "MySQL", "weight": 1., "difficulty": "mid",
                              "question_count": 1, "include_coding": False}]}
        elif "评分官" in prompt:
            component = "scorer"
            inputs = json.loads(body["messages"][1]["content"])
            answer = inputs["candidate_answer"]
            assert answer in llm_ping.SCORE_CASES.values()
            assert inputs["reference_points"] == [{"point": p.point, "keywords": list(p.keywords)}
                                                   for p in question.answer_points]
            points = [p.point for p in question.answer_points]
            short = answer == llm_ping.SCORE_CASES["short"]
            data = {"score": 1. if short else 8.,
                    "dimensions": {"技术深度": 1. if short else 8., "表达逻辑": 7., "岗位匹配": 6.},
                    "key_points_hit": [] if short else points, "key_points_missed": points if short else [],
                    "evidence": "合成测试", "evidence_quotes": [answer]}
        else:
            component = "prober"
            target = json.loads(body["messages"][1]["content"])
            data = {"content": "请说明" + "、".join(target["points"]), "node_id": target["node_id"]}
        count[component] += 1
        fault = faults.get((component, count[component]))
        return response("bad-json" if fault == "invalid" else json.dumps(data, ensure_ascii=False),
                        usage=fault != "usage")
    llm = client(handler)
    monkeypatch.setattr(llm_ping, "build_llm", lambda settings: llm)
    yield config, count, faults
    configure_strict(False)


def test_probe_disables_cache_and_verifies_every_repeat(probe):
    config, count, faults = probe
    report = llm_ping.run_probe(config, repeats=2)
    assert report["all_llm_success"] and not report["scoring_cache_enabled"]
    assert count == {key: 2 for key in count}
    assert report["usage"]["network_calls"] == 8
    assert sum(r["tokens_reported"] for r in report["components"]) == 120


@pytest.mark.parametrize("case", ["short", "mixed"])
def test_probe_forwards_synthetic_answer_variants(probe, case):
    config, count, faults = probe
    report = llm_ping.run_probe(config, strict=True, score_case=case)
    assert report["all_llm_success"]
    assert report["synthetic_inputs"]["score_case"] == case
    assert report["synthetic_inputs"]["answer_chars"] == len(llm_ping.SCORE_CASES[case])
    assert count == {key: 1 for key in count}


def test_one_success_cannot_hide_later_fallback(probe):
    config, count, faults = probe
    faults[("resume_parser", 2)] = "invalid"
    report = llm_ping.run_probe(config, repeats=2)
    assert report["failed_components"] == ["resume_parser"]
    row = report["components"][0]
    assert row["outcome"] == "heuristic_fallback" and row["llm_success"] == 1
    assert not report["all_llm_success"]


def test_strict_failure_reports_and_continues_other_components(probe):
    config, count, faults = probe
    faults[("scorer", 1)] = "invalid"
    report = llm_ping.run_probe(config, strict=True)
    assert report["failed_components"] == ["scorer"]
    assert report["attempts"][-1]["probe_input"] == "synthetic_baseline"
    assert count["prober"] == 1 and not strict_enabled()


def test_missing_usage_not_reported_as_verified_success(probe):
    config, count, faults = probe
    faults[("resume_parser", 1)] = "usage"
    report = llm_ping.run_probe(config)
    assert report["failed_components"] == ["resume_parser"]
    assert report["components"][0]["outcome"] == "unverified_usage"


def test_cli_setup_failure_still_writes_safe_report(tmp_path, monkeypatch, capsys):
    def broken(**kwargs): raise ValueError("synthetic-secret")
    monkeypatch.setattr(llm_ping, "Settings", broken)
    path = tmp_path / "nested/result.json"
    assert llm_ping.main(["--strict", "--json-out", str(path)]) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "setup_failed"
    assert "synthetic-secret" not in capsys.readouterr().out


@pytest.mark.parametrize("enabled", [False, True])
def test_e2e_remote_llm_requires_explicit_switch(monkeypatch, enabled):
    import tempfile
    from evals import smoke_e2e
    monkeypatch.setenv("LLM_API_KEY", "synthetic-env-key")
    with tempfile.TemporaryDirectory(prefix=".llm-server-test-", dir=smoke_e2e.BACKEND) as directory:
        server = smoke_e2e.Server(Path(directory) / "test.sqlite3", use_llm=enabled)
        def launch(command, **kwargs):
            env = kwargs["env"]
            assert env["LLM_API_KEY"] == ("synthetic-env-key" if enabled else "")
            if enabled:
                assert env["LLM_STRICT_MODE"] == "true" and env["SCORING_CACHE_ENABLED"] == "false"
                assert env["MAX_PLAN_THEMES"] == env["PROBE_DEPTH_LIMIT"] == "1"
            server.pid_file.write_text("1234")
            return type("Process", (), {"poll": lambda self: None})()
        monkeypatch.setattr(smoke_e2e.subprocess, "Popen", launch)
        monkeypatch.setattr(smoke_e2e, "request", lambda *a, **kw: {"process_id": 1234})
        server.start()


def test_e2e_setup_failure_preserves_safe_report(tmp_path, monkeypatch, capsys):
    from evals import smoke_e2e
    class BrokenServer:
        process = None
        def __init__(self, *a, **kw): pass
        def start(self): raise RuntimeError("synthetic-env-key")
        def stop(self): pass
    monkeypatch.setattr(smoke_e2e, "Server", BrokenServer)
    monkeypatch.setattr(sys, "argv", ["smoke_e2e", "--start-server", "--llm", "--json-out", str(tmp_path / "fail.json")])
    assert smoke_e2e.main() == 1
    data = json.loads((tmp_path / "fail.json").read_text(encoding="utf-8"))
    assert data["result"] == "failed" and data["error_category"] == "RuntimeError"
    assert "synthetic-env-key" not in capsys.readouterr().out
