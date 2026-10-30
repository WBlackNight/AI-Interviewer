"""四组件真实联调；逐次检查遥测和用量，严格失败也保存报告。

从任意目录读取backend/.env。合成数据、禁用评分缓存。
退出0=全部成功且用量已知；1=失败/回退/未知用量；2=缺少配置。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import Settings
from app.domain import ResumeData
from app.agent.scorer import HeuristicScorer, LLMScorer
from app.factories import build_llm, build_planner, build_prober, load_assets
from app.llm.errors import classify_exception
from app.llm.resilience import configure_strict, strict_enabled
from app.llm.telemetry import get_telemetry
from app.rag.resume_parser import parse_resume_text_with_llm

SYNTHETIC_ANSWER = (
    "B+树是多路平衡搜索树，叶子节点用链表连接，所以支持范围查询；"
    "相比哈希索引，它的磁盘IO次数更少，因为树高通常只有三四层。"
    "我在项目里做过联合索引优化，用 explain 分析过执行计划。"
)
SYNTHETIC_RESUME = (
    "教育经历\n某大学 计算机科学与技术 本科\n"
    "专业技能\nJava、Spring、MySQL、Redis、并发编程、JVM\n"
    "项目经历\n电商秒杀系统：负责库存超卖防护与缓存一致性设计\n"
)
SCORE_CASES = {
    "baseline": SYNTHETIC_ANSWER,
    "short": "我只知道索引有助于加速查询，具体结构还不清楚。",
    "mixed": (
        "B+树是多路平衡搜索树，支持范围查询，叶子链表降低磁盘IO。"
        "MVCC通过undo版本链与快照实现隔离。线程池核心线程、队列、最大线程、拒绝策略。"
        "JVM运行时数据区包括堆、虚拟机栈、方法区、程序计数器，区分线程私有与共享，"
        "OOM内存溢出需要GC垃圾回收。Redis缓存穿透使用布隆过滤器，热点击穿用互斥锁，"
        "雪崩时随机过期，我们实际项目做过方案优化。"
    ),
}
COMPONENTS = ("resume_parser", "planner", "scorer", "prober")


def _outcome_of(stats: dict, expected: int = 1) -> str:
    if not stats.get("calls"):
        return "not_run"
    if stats.get("error_raised"):
        return "error_raised"
    if stats.get("heuristic_fallback"):
        return "heuristic_fallback"
    if stats.get("calls") == expected and stats.get("llm_success") == expected:
        return "llm_success"
    return "incomplete"


def run_probe(settings: Settings, *, repeats: int = 1, strict: bool = False,
              score_case: str = "baseline") -> dict:
    if not 1 <= repeats <= 10:
        raise ValueError("repeat must be 1..10")
    answer = SCORE_CASES[score_case]
    trees, bank = load_assets(settings)
    tree = trees["java_backend"]
    # The synthetic answer and planner probe below are Java-specific.
    question = bank.get('jv-mysql-index-001')
    llm = build_llm(settings)
    if llm is None:
        raise ValueError("not_configured")
    # 直接构造无缓存评分器，避免现有进程缓存造成虚假成功。
    scorer = LLMScorer(llm)
    telemetry = get_telemetry()
    telemetry.reset()
    previous_strict = strict_enabled()
    configure_strict(strict)
    attempts = []
    result = None

    def timed(component, iteration, fn):
        before = telemetry.snapshot().get(component, {})
        usage_before = llm.usage_diagnostics()
        started = time.monotonic()
        error_kind, value = None, None
        try:
            value = fn()
        except Exception as exc:
            error_kind = classify_exception(exc).value
        after = telemetry.snapshot().get(component, {})
        delta = {key: after.get(key, 0) - before.get(key, 0)
                 for key in ("calls", "llm_success", "heuristic_fallback", "error_raised")}
        usage_after = llm.usage_diagnostics()
        usage = {key: usage_after[key] - usage_before[key]
                 for key in ("tokens_in", "tokens_out", "network_calls", "unknown_usage_calls")}
        outcome = "error_raised" if error_kind else _outcome_of(delta)
        if outcome == "llm_success" and (usage["network_calls"] < 1 or usage["unknown_usage_calls"]):
            outcome = "unverified_usage"
        attempts.append({"iteration": iteration, "component": component, "outcome": outcome,
                         "error_kind": error_kind, "latency_ms": (time.monotonic() - started) * 1000,
                         "usage": usage})
        return value

    try:
        for iteration in range(1, repeats + 1):
            timed("resume_parser", iteration, lambda: parse_resume_text_with_llm(SYNTHETIC_RESUME, llm))
            timed("planner", iteration, lambda: build_planner(settings, llm, tree).build_plan(
                position="java_backend", difficulty="mid",
                resume=ResumeData(skills=["Java", "MySQL"], projects=[], education=""),
                bank=bank, max_themes=2))
            result = timed("scorer", iteration, lambda: scorer.score(question, answer))
            # 评分失败仍独立测试追问；此基线只作为追问输入，不冒充模型成功。
            probe_input = result or HeuristicScorer().score(question, answer)
            timed("prober", iteration, lambda: build_prober(settings, llm, tree).propose(
                question, probe_input, 1, answer=answer))
            attempts[-1]["probe_input"] = "scorer_result" if result else "synthetic_baseline"
        total_usage = llm.usage_diagnostics()
    finally:
        llm.close()
        configure_strict(previous_strict)

    snapshot, rows = telemetry.snapshot(), []
    for component in COMPONENTS:
        samples = [row for row in attempts if row["component"] == component]
        stats = snapshot.get(component, {})
        success = len(samples) == repeats and all(row["outcome"] == "llm_success" for row in samples)
        outcome = "llm_success" if success else _outcome_of(stats, repeats)
        if not success and outcome == "llm_success":
            outcome = "unverified_usage"
        rows.append({"component": component, "outcome": outcome,
            "all_attempts_passed": success, "calls": stats.get("calls", 0),
            "llm_success": stats.get("llm_success", 0),
            "heuristic_fallback": stats.get("heuristic_fallback", 0),
            "error_raised": stats.get("error_raised", 0), "error_kinds": stats.get("error_kinds", {}),
            "validation_reasons": stats.get("validation_reasons", {}),
            "tokens_reported": sum(row["usage"]["tokens_in"] + row["usage"]["tokens_out"] for row in samples),
            "latency_ms_p50": statistics.median(row["latency_ms"] for row in samples),
            "latency_ms_max": max(row["latency_ms"] for row in samples)})
    failed = [row["component"] for row in rows if not row["all_attempts_passed"]]
    return {"provider_host": urlsplit(settings.llm_base_url).hostname, "model": settings.llm_model,
        "strict_mode": strict, "repeat": repeats, "scoring_cache_enabled": False,
        "request_config": {"max_output_tokens": settings.llm_max_output_tokens,
                           "thinking_mode": settings.llm_thinking_mode, "max_attempts": settings.llm_max_attempts},
        "synthetic_inputs": {"score_case": score_case, "answer_chars": len(answer),
                             "resume_chars": len(SYNTHETIC_RESUME)},
        "components": rows, "attempts": attempts, "usage": total_usage,
        "all_llm_success": not failed, "failed_components": failed,
        "score_sample": {"score": result.score, "dimensions": result.dimensions,
                         "evidence_ref_count": len(result.evidence_refs)} if result else None,
        "latency_note": "合成数据连通性采样；不代表独立评分质量、可重复性或容量指标"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--score-case", choices=tuple(SCORE_CASES), default="baseline")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        settings = Settings(_env_file=BACKEND / ".env")
        if not settings.llm_api_key:
            report, code = {"all_llm_success": False, "status": "not_configured"}, 2
        else:
            report = run_probe(settings, repeats=args.repeat, strict=args.strict, score_case=args.score_case)
            code = 0 if report["all_llm_success"] else 1
    except Exception as exc:
        report, code = {"all_llm_success": False, "status": "setup_failed",
                        "error_kind": classify_exception(exc).value}, 1
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return code


if __name__ == "__main__":
    sys.exit(main())
