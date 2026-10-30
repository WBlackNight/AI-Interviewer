"""将已有报告导出为可携带文本；不调用模型，不附加访问凭据。"""
import html
import re
from app.score_origin import read_origin

SOURCE_LABELS = {"heuristic": "规则评分", "llm": "模型评分", "heuristic_fallback": "模型失败后规则回退", "unknown": "来源未记录"}


def _inline(value) -> str:
    text = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", text)


def _block(value) -> str:
    text = str(value or "（无）")
    # 用户原文可以包含任意代码围栏；动态长度保证原文不能提前闭合代码块。
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def render_markdown(report: dict) -> str:
    complete = report["is_complete"]
    rows = ["# 面试复盘报告", "", f"- 岗位：{_inline(report['position'])}",
            f"- 状态：{'已取消（部分报告）' if report.get('is_cancelled') else '已完成' if complete else '进行中（部分报告）'}",
            f"- 主问题：{report['question_count']}；回答轮数：{report['answer_count']}",
            f"- 综合得分：{report['overall'] if report['overall'] is not None else '暂无评分'} / 10",
            f"- 开始时间：{_inline(report['started_at'] or '尚未开始')}",
            f"- 结束时间：{_inline(report['ended_at'] or '尚未结束')}", "",
            "这是系统生成的练习反馈，可能包含启发式回退，不等同于人工评定。", "",
            "## 能力维度", ""]
    rows.extend(f"- {_inline(key)}：{value} / 10" for key, value in report["dimensions"].items())
    if source := report.get("revision_source"):
        rows.extend(["", "## 复习任务来源", "",
            f"- 主题：{_inline(source['theme'])}", f"- 任务ID：{_inline(source['task_id'])}",
            f"- 原报告ID：{_inline(source['interview_id'])}", "",
            "练习完成不会自动改变任务的手动复习状态。"])
    rows.extend(["", "## 复习建议", ""])
    rows.extend(f"- {_inline(tip)}" for tip in report["recommendations"])
    if not report["recommendations"]:
        rows.append("暂无复习建议。")
    rows.extend(["", "## 逐轮复盘", ""])
    for i, turn in enumerate(report["per_question"], 1):
        origin = read_origin(turn.get("scoring_origin"))
        source = SOURCE_LABELS[origin["source"]] + ("（缓存命中，本轮未调用评分模型）" if origin["cached"] else "")
        versions = "；".join(f"{key}={origin[key]}" for key in
            ("scorer_version", "model", "prompt_version", "prompt_digest", "config_version", "fallback_reason") if origin.get(key))
        rows.extend([f"### 第{i}轮 · {_inline(turn['theme'])}", "",
            f"得分：{turn['score']} / 10；追问深度：{turn['probe_depth']}", "",
            "评分来源：" + _inline(source), "", "来源版本：" + (_inline(versions) or "未记录"), "",
            "题目：", "", _block(turn["content"]), "", "回答：", "", _block(turn["answer_text"]),
            "", "评分依据：", "", _block(turn["evidence"]), "",
            "命中要点：" + (_inline("、".join(turn["key_points_hit"])) or "无"), "",
            "待补强：" + (_inline("、".join(turn["key_points_missed"])) or "无"), ""])
        if turn.get("sandbox"):
            sandbox = turn["sandbox"]
            rows.extend([f"客观判题：{sandbox['passed']}/{sandbox['total']} 用例通过。", ""])
    if not report["per_question"]:
        rows.append("尚无已评分回答。")
    rows.extend(["", "聚合方式：" + _inline(report["aggregation"]), ""])
    return "\n".join(rows)
