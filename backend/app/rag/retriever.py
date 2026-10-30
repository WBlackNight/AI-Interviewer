"""召回接口与统一候选过滤。难度仅在没有未问题时按显式策略放宽。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from rank_bm25 import BM25Okapi

from app.domain import Question


@dataclass(frozen=True)
class QuestionFilter:
    position: str
    theme: str | None = None
    difficulty: str | None = None
    is_coding: bool = False
    exclude: frozenset[str] = field(default_factory=frozenset)
    relax_difficulty: bool = True


def candidates(questions: Sequence[Question], filters: QuestionFilter) -> list[Question]:
    base = [q for q in questions if q.position == filters.position
            and (filters.theme is None or q.theme == filters.theme)
            and q.is_coding == filters.is_coding and q.id not in filters.exclude]
    if filters.difficulty is None:
        return base
    exact = [q for q in base if q.difficulty == filters.difficulty]
    return exact or (base if filters.relax_difficulty else [])


def document_text(question: Question) -> str:
    # BM25与向量支路用同一输入，不把参考答案作为某个支路的额外信息。
    return f"{question.theme} {question.content}"


def tokenize(text: str) -> list[str]:
    return [ch for ch in text.lower() if not ch.isspace()]


@dataclass(frozen=True)
class Hit:
    question_id: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    hits: tuple[Hit, ...]
    requested: str
    actual: str
    fallback_reason: str | None = None


class Retriever(Protocol):
    @property
    def version(self) -> str: ...
    def search(self, query: str, pool: Sequence[Question], limit: int) -> RetrievalResult: ...
    def diagnostics(self) -> dict: ...


class BM25Retriever:
    version = "bm25-v1"

    def __init__(self, questions: Sequence[Question]):
        self._questions = list(questions)
        self._bm25 = BM25Okapi([tokenize(document_text(q)) for q in questions]) if questions else None

    def search(self, query: str, pool: Sequence[Question], limit: int) -> RetrievalResult:
        if limit < 1:
            raise ValueError("limit必须为正数")
        if not pool:
            return RetrievalResult((), "bm25", "bm25")
        scores = self._bm25.get_scores(tokenize(query)) if self._bm25 else []
        by_id = {q.id: float(scores[i]) for i, q in enumerate(self._questions)}
        hits = sorted((Hit(q.id, by_id.get(q.id, 0.0)) for q in pool), key=lambda h: -h.score)
        return RetrievalResult(tuple(hits[:limit]), "bm25", "bm25")

    def diagnostics(self) -> dict:
        return {"requested": "bm25", "version": self.version, "index_state": "not_required",
                "semantic_model": False}
