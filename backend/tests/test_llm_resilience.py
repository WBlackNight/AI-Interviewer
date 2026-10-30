"""LLM 加固与可观测回退测试（P2 步骤 2.1 验收）。

评审验收要求：
- **四个组件**（简历抽取 / 规划 / 评分 / 追问）分别有
  **成功、超时、非法 JSON、字段类型错误**用例；
- **网络失败不把启发式结果标成"LLM 验证成功"**——这是本文件的断言核心。

单元测试一律使用 Fake LLM，不触网；真实服务联调走 `evals/llm_ping.py`。
"""
from __future__ import annotations

import json

import pytest

from app.agent.planner import HeuristicPlanner, LLMPlanner
from app.agent.prober import LLMProber, SkillTreeProber
from app.agent.scorer import HeuristicScorer, LLMScorer
from app.config import get_settings
from app.domain import AnswerPoint, Question, ResumeData
from app.factories import load_assets
from app.llm.budget import TokenBudget, use_budget
from app.llm.client import OpenAICompatibleLLM
from app.llm.errors import (
    BudgetExceeded,
    LLMError,
    LLMErrorKind,
    as_llm_error,
    classify_exception,
)
from app.llm.resilience import call_with_fallback, configure_strict, handle_fallback
from app.llm.telemetry import CallOutcome, LLMTelemetry
from app.rag.resume_parser import parse_resume_text_with_llm


# ---------------------------------------------------------------- 测试替身


class APITimeoutError(Exception):
    """类名与 openai 一致：分类器按类名兜底匹配，这里正好验证该机制。"""


class FakeLLM:
    def __init__(self, *, response: str | None = None, exc: BaseException | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[list[dict]] = []

    def chat(self, messages, *, json_mode=False, temperature=None) -> str:
        self.calls.append(messages)
        if self.exc is not None:
            raise self.exc
        assert self.response is not None, "FakeLLM 需要 response 或 exc"
        return self.response


@pytest.fixture
def telemetry(monkeypatch) -> LLMTelemetry:
    """每个用例独立遥测，并让它成为组件的实际记录目标。

    组件通过 ``app.llm.resilience.get_telemetry`` 取遥测，因此替换点必须在那里；
    早先误把替换点写成各组件模块，导致断言到了一份空计数。
    """
    from app.llm import resilience

    instance = LLMTelemetry()
    monkeypatch.setattr(resilience, "get_telemetry", lambda: instance)
    return instance


@pytest.fixture(autouse=True)
def _reset_strict():
    configure_strict(False)
    yield
    configure_strict(False)


@pytest.fixture(scope="module")
def assets():
    trees, bank = load_assets(get_settings())
    return trees["java_backend"], bank


@pytest.fixture
def question() -> Question:
    return Question(
        id="q-test-1", position="java_backend", theme="MySQL", difficulty="mid",
        content="请讲讲 B+ 树索引的结构与优势。",
        answer_points=(
            AnswerPoint(point="B+树结构", keywords=("b+树", "多路")),
            AnswerPoint(point="范围查询", keywords=("范围查询", "链表")),
        ),
    )


ANSWER = "B+树是多路平衡搜索树，叶子节点用链表连接，所以支持范围查询。"
FAKE_RESUME = "专业技能\nJava、MySQL\n项目经历\n秒杀系统\n"


# ---------------------------------------------------------------- 错误分类


class TestErrorClassification:
    def test_timeout_by_class_name(self):
        assert classify_exception(APITimeoutError("slow")) is LLMErrorKind.TIMEOUT

    def test_status_code_mapping(self):
        class WithStatus(Exception):
            status_code = 429

        assert classify_exception(WithStatus()) is LLMErrorKind.RATE_LIMIT

    def test_server_error_status(self):
        class WithStatus(Exception):
            status_code = 503

        assert classify_exception(WithStatus()) is LLMErrorKind.SERVER

    def test_bad_request_not_retryable(self):
        class WithStatus(Exception):
            status_code = 400

        error = as_llm_error(WithStatus("bad"))
        assert error.kind is LLMErrorKind.BAD_REQUEST
        assert error.retryable is False

    def test_value_error_family_is_bad_payload(self):
        assert classify_exception(ValueError("x")) is LLMErrorKind.BAD_PAYLOAD
        assert classify_exception(KeyError("x")) is LLMErrorKind.BAD_PAYLOAD
        assert classify_exception(TypeError("x")) is LLMErrorKind.BAD_PAYLOAD

    def test_retryable_set(self):
        assert as_llm_error(APITimeoutError()).retryable is True
        assert as_llm_error(ValueError()).retryable is False

    def test_as_llm_error_is_idempotent(self):
        original = LLMError(LLMErrorKind.AUTH, "key 无效")
        assert as_llm_error(original) is original


# ---------------------------------------------------------------- 遥测


class TestTelemetry:
    def test_records_outcomes_separately(self):
        telemetry = LLMTelemetry()
        telemetry.record("scorer", CallOutcome.LLM_SUCCESS)
        telemetry.record("scorer", CallOutcome.HEURISTIC_FALLBACK,
                         error_kind=LLMErrorKind.TIMEOUT)
        stats = telemetry.snapshot()["scorer"]
        assert stats["calls"] == 2
        assert stats["llm_success"] == 1
        assert stats["heuristic_fallback"] == 1
        assert stats["fallback_rate"] == 0.5
        assert stats["error_kinds"] == {"timeout": 1}

    def test_snapshot_exposes_no_secrets(self):
        telemetry = LLMTelemetry()
        telemetry.record("scorer", CallOutcome.HEURISTIC_FALLBACK,
                         error_kind=LLMErrorKind.TIMEOUT)
        payload = json.dumps(telemetry.snapshot(), ensure_ascii=False)
        for forbidden in ("sk-", "api_key", "Bearer"):
            assert forbidden not in payload


# ---------------------------------------------------------------- 回退策略


class TestResilience:
    def test_success_returns_primary_value(self, telemetry):
        value = call_with_fallback(
            component="scorer", primary=lambda: "llm值", fallback=lambda: "启发式值"
        )
        assert value == "llm值"
        assert telemetry.snapshot()["scorer"]["llm_success"] == 1

    def test_failure_returns_fallback_and_is_observable(self, telemetry):
        def boom():
            raise APITimeoutError("timeout")

        value = call_with_fallback(
            component="scorer", primary=boom, fallback=lambda: "启发式值"
        )
        assert value == "启发式值"
        stats = telemetry.snapshot()["scorer"]
        assert stats["heuristic_fallback"] == 1
        assert stats["llm_success"] == 0, "回退绝不能被记成 LLM 成功"
        assert stats["error_kinds"] == {"timeout": 1}

    def test_strict_mode_raises_instead_of_falling_back(self, telemetry):
        def boom():
            raise ValueError("非法 JSON")

        with pytest.raises(LLMError) as info:
            call_with_fallback(
                component="scorer", primary=boom, fallback=lambda: "启发式值", strict=True
            )
        assert info.value.kind is LLMErrorKind.BAD_PAYLOAD
        assert telemetry.snapshot()["scorer"]["error_raised"] == 1

    def test_budget_exceeded_never_falls_back(self, telemetry):
        """预算超限是策略性中止，必须上抛——否则预算保护会静默失效。"""

        def over_budget():
            raise BudgetExceeded("预算已耗尽")

        with pytest.raises(BudgetExceeded):
            call_with_fallback(
                component="scorer", primary=over_budget,
                fallback=lambda: pytest.fail("不应回退"),
            )
        assert telemetry.snapshot().get("scorer", {}).get("heuristic_fallback", 0) == 0

    def test_handle_fallback_shares_policy(self, telemetry):
        try:
            raise APITimeoutError("slow")
        except APITimeoutError as exc:
            value = handle_fallback(component="planner", exc=exc, fallback=lambda: "回退值")
        assert value == "回退值"
        assert telemetry.snapshot()["planner"]["error_kinds"] == {"timeout": 1}

    def test_handle_fallback_reraises_budget(self, telemetry):
        with pytest.raises(BudgetExceeded):
            handle_fallback(
                component="planner", exc=BudgetExceeded("x"),
                fallback=lambda: pytest.fail("不应回退"),
            )


# ---------------------------------------------------------------- 四类响应构造

SCORER_RESPONSE = json.dumps({
    "score": 8.0,
    "dimensions": {"技术深度": 8.0, "表达逻辑": 7.0, "岗位匹配": 8.0},
    "key_points_hit": ["B+树结构"],
    "key_points_missed": ["范围查询"],
    "evidence": "候选人说明了 B+树结构",
    # 必须是回答的逐字子串，否则会被判为伪造引用
    "evidence_quotes": ["B+树是多路平衡搜索树"],
}, ensure_ascii=False)

RESUME_RESPONSE = json.dumps(
    {"skills": ["Java", "MySQL"], "projects": ["秒杀系统"], "education": "某大学"},
    ensure_ascii=False,
)

FAILURE_MODES = ("timeout", "invalid_json", "wrong_type")


def _break_first_field(node) -> bool:
    """把第一个可改的叶值换成类型不符的值，制造"字段类型错误"。

    递归查找而非只看顶层：prober 的响应里没有数值字段，
    只盯数值会构造不出该用例（这正是第一版的缺陷）。
    """
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, bool):
                node[key] = "not_a_bool"
                return True
            if isinstance(value, str):
                node[key] = 12345
                return True
            if isinstance(value, (int, float)):
                node[key] = "text_instead_of_number"
                return True
            if isinstance(value, (dict, list)) and _break_first_field(value):
                return True
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)) and _break_first_field(item):
                return True
    return False


def _failure_response(mode: str, good_json: str) -> FakeLLM:
    if mode == "timeout":
        return FakeLLM(exc=APITimeoutError("request timed out"))
    if mode == "invalid_json":
        return FakeLLM(response="这不是 JSON")
    if mode == "wrong_type":
        data = json.loads(good_json)
        assert _break_first_field(data), "未能构造出字段类型错误"
        broken = json.dumps(data, ensure_ascii=False)
        assert broken != good_json
        return FakeLLM(response=broken)
    raise AssertionError(mode)


def _prober_response(assets, question: Question, result) -> str:
    tree, _bank = assets
    target = SkillTreeProber(tree).propose(question, result, 1, answer=ANSWER)
    content = "请进一步说明" + "、".join(p.point for p in target.points)
    return json.dumps({"content": content, "node_id": target.node_id}, ensure_ascii=False)


def _planner_response(assets) -> str:
    tree, bank = assets
    root = next(
        r for r in tree.root_names()
        if bank.next_question(position="java_backend", theme=r, difficulty="mid", exclude=set())
    )
    # include_coding=False：避免依赖该主题恰好有编码题
    return json.dumps({"plan": [{
        "theme": root, "weight": 1.0, "difficulty": "mid",
        "question_count": 1, "include_coding": False,
    }]}, ensure_ascii=False)


# ---------------------------------------------------------------- 四个组件 × 四类响应


class TestFourComponentsUnderFailureModes:
    """评审验收：四个组件各有成功/超时/非法JSON/字段类型错误用例。"""

    # ---- 评分
    def test_scorer_success(self, question, telemetry):
        result = LLMScorer(FakeLLM(response=SCORER_RESPONSE)).score(question, ANSWER)
        assert result.score == 8.0
        assert result.key_points_hit == ("B+树结构",)
        assert telemetry.snapshot()["scorer"]["llm_success"] == 1

    @pytest.mark.parametrize("mode", FAILURE_MODES)
    def test_scorer_failure_falls_back(self, mode, question, telemetry):
        llm = _failure_response(mode, SCORER_RESPONSE)
        result = LLMScorer(llm).score(question, ANSWER)
        expected = HeuristicScorer().score(question, ANSWER)
        assert result.score == expected.score, "回退必须产出启发式结果"
        stats = telemetry.snapshot()["scorer"]
        assert stats["llm_success"] == 0
        assert stats["heuristic_fallback"] == 1
        assert stats["error_kinds"], "错误类别必须可观察"

    # ---- 追问
    def test_prober_success(self, assets, question, telemetry):
        tree, _ = assets
        result = HeuristicScorer().score(question, ANSWER)
        baseline = SkillTreeProber(tree).propose(question, result, 1, answer=ANSWER)
        llm = FakeLLM(response=_prober_response(assets, question, result))
        got = LLMProber(llm, tree).propose(question, result, 1, answer=ANSWER)
        assert got.node_id == baseline.node_id, "目标节点不可被模型改变"
        assert got.content != baseline.content, "成功时应使用模型措辞"
        assert telemetry.snapshot()["prober"]["llm_success"] == 1

    @pytest.mark.parametrize("mode", FAILURE_MODES)
    def test_prober_failure_falls_back(self, mode, assets, question, telemetry):
        tree, _ = assets
        result = HeuristicScorer().score(question, ANSWER)
        baseline = SkillTreeProber(tree).propose(question, result, 1, answer=ANSWER)
        llm = _failure_response(mode, _prober_response(assets, question, result))
        got = LLMProber(llm, tree).propose(question, result, 1, answer=ANSWER)
        assert got.content == baseline.content, "回退必须产出技能树方案"
        assert telemetry.snapshot()["prober"]["llm_success"] == 0

    # ---- 规划
    def test_planner_success(self, assets, telemetry):
        tree, bank = assets
        llm = FakeLLM(response=_planner_response(assets))
        plan = LLMPlanner(llm, tree).build_plan(
            position="java_backend", difficulty="mid",
            resume=ResumeData(skills=["Java"], projects=[], education=""),
            bank=bank, max_themes=2,
        )
        assert plan
        assert telemetry.snapshot()["planner"]["llm_success"] == 1

    @pytest.mark.parametrize("mode", FAILURE_MODES)
    def test_planner_failure_falls_back(self, mode, assets, telemetry):
        tree, bank = assets
        resume = ResumeData(skills=["Java"], projects=[], education="")
        llm = _failure_response(mode, _planner_response(assets))
        plan = LLMPlanner(llm, tree).build_plan(
            position="java_backend", difficulty="mid", resume=resume, bank=bank, max_themes=2,
        )
        expected = HeuristicPlanner(tree).build_plan(
            position="java_backend", difficulty="mid", resume=resume, bank=bank, max_themes=2,
        )
        assert [p.theme for p in plan] == [p.theme for p in expected]
        assert telemetry.snapshot()["planner"]["llm_success"] == 0

    # ---- 简历抽取
    def test_resume_parser_success(self, telemetry):
        data = parse_resume_text_with_llm(FAKE_RESUME, FakeLLM(response=RESUME_RESPONSE))
        assert data.skills == ["Java", "MySQL"]
        assert telemetry.snapshot()["resume_parser"]["llm_success"] == 1

    @pytest.mark.parametrize("mode", FAILURE_MODES)
    def test_resume_parser_failure_falls_back(self, mode, telemetry):
        llm = _failure_response(mode, RESUME_RESPONSE)
        data = parse_resume_text_with_llm(FAKE_RESUME, llm)
        assert isinstance(data.skills, list) and data.skills, "规则解析兜底应至少抽出技能"
        stats = telemetry.snapshot()["resume_parser"]
        assert stats["llm_success"] == 0
        assert stats["heuristic_fallback"] == 1


class TestStrictModeExposesDefects:
    @pytest.mark.parametrize("mode", FAILURE_MODES)
    def test_components_raise_in_strict_mode(self, mode, question, telemetry):
        """严格模式让静默回退变成显式异常，避免缺陷被掩盖。"""
        configure_strict(True)
        llm = _failure_response(mode, SCORER_RESPONSE)
        with pytest.raises(LLMError):
            LLMScorer(llm).score(question, ANSWER)
        assert telemetry.snapshot()["scorer"]["error_raised"] == 1


# ---------------------------------------------------------------- 客户端重试与预算


class _FakeCompletion:
    def __init__(self, content: str | None, tokens=(10, 5)) -> None:
        message = type("Message", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": message})()]
        self.usage = type("Usage", (), {
            "prompt_tokens": tokens[0], "completion_tokens": tokens[1],
        })()


class TestClientRetryAndBudget:
    @staticmethod
    def _client(outcomes: list, **kwargs):
        client = OpenAICompatibleLLM(
            api_key="test-key", base_url="http://127.0.0.1:9/v1", model="test-model", **kwargs
        )
        calls: list[int] = []

        class FakeCompletions:
            def create(self, **payload):
                calls.append(1)
                outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        client._client = type("FakeOpenAI", (), {
            "chat": type("Chat", (), {"completions": FakeCompletions()})(),
            "close": lambda self: None,
        })()
        return client, calls

    def test_retryable_error_is_retried(self):
        client, calls = self._client(
            [APITimeoutError("t"), _FakeCompletion("ok")],
            max_attempts=3, backoff_base_seconds=0.001,
        )
        assert client.chat([{"role": "user", "content": "hi"}]) == "ok"
        assert len(calls) == 2, "可重试错误应先重试再成功"

    def test_non_retryable_error_is_not_retried(self):
        class BadRequest(Exception):
            status_code = 400

        client, calls = self._client(
            [BadRequest("bad")], max_attempts=3, backoff_base_seconds=0.001
        )
        with pytest.raises(LLMError) as info:
            client.chat([{"role": "user", "content": "hi"}])
        assert info.value.kind is LLMErrorKind.BAD_REQUEST
        assert len(calls) == 1, "4xx 重试无用，不应重试"

    def test_retries_exhausted_raises_last_kind(self):
        client, calls = self._client(
            [APITimeoutError("t")], max_attempts=2, backoff_base_seconds=0.001
        )
        with pytest.raises(LLMError) as info:
            client.chat([{"role": "user", "content": "hi"}])
        assert info.value.kind is LLMErrorKind.TIMEOUT
        assert len(calls) == 2

    def test_empty_content_treated_as_retryable(self):
        client, calls = self._client(
            [_FakeCompletion(None), _FakeCompletion("ok")],
            max_attempts=2, backoff_base_seconds=0.001,
        )
        assert client.chat([{"role": "user", "content": "hi"}]) == "ok"
        assert len(calls) == 2

    def test_usage_is_accumulated_from_response(self):
        client, _ = self._client([_FakeCompletion("ok", tokens=(30, 20))])
        client.chat([{"role": "user", "content": "hi"}])
        client.chat([{"role": "user", "content": "hi"}])
        assert client.usage == {"tokens_in": 60, "tokens_out": 40}

    def test_budget_is_charged_and_can_block(self):
        client, _ = self._client([_FakeCompletion("ok", tokens=(100, 100))])
        # 每次调用 200 token：上限 300 时第一次通过、第二次超限。
        budget = TokenBudget(limit_tokens=300)
        with use_budget(budget):
            client.chat([{"role": "user", "content": "hi"}])
            with pytest.raises(BudgetExceeded):
                client.chat([{"role": "user", "content": "hi"}])
        assert budget.used_tokens == 400, "超限的那次用量也必须记账"

    def test_budget_without_prices_reports_tokens_only(self):
        budget = TokenBudget(limit_tokens=100)
        budget.charge(tokens_in=10, tokens_out=10)
        snapshot = budget.snapshot()
        assert snapshot["used_cost"] is None
        assert "不计算金额" in snapshot["cost_note"]

    def test_budget_with_prices_computes_cost(self):
        budget = TokenBudget(
            limit_tokens=0, limit_cost=10.0,
            price_input_per_million=2.0, price_output_per_million=8.0,
        )
        budget.charge(tokens_in=500_000, tokens_out=100_000)
        assert round(budget.used_cost, 6) == round(0.5 * 2.0 + 0.1 * 8.0, 6)

    def test_rejects_invalid_construction(self):
        with pytest.raises(ValueError):
            OpenAICompatibleLLM(api_key="k", base_url="http://x", model="m", max_attempts=0)
        with pytest.raises(ValueError):
            OpenAICompatibleLLM(api_key="k", base_url="http://x", model="m", max_concurrency=0)
