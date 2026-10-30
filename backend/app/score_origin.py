"""评分来源与题目版本的纯转换；不读取当前模型配置来解释历史。"""
from dataclasses import asdict
import hashlib
import json

from app.domain import Question, ScoreOrigin

SOURCES = ("heuristic", "llm", "heuristic_fallback", "unknown")


def question_version(question: Question) -> str:
    return hashlib.sha256(json.dumps(asdict(question), ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_origin(data: dict | None) -> dict:
    result = {**asdict(ScoreOrigin()), **(data or {})}
    if result["source"] not in SOURCES:
        result["source"] = "unknown"
    return result
