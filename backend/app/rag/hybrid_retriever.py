"""BM25/离线向量/RRF共享候选池；向量故障可观察地回退到BM25。"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Sequence

from app.domain import Question
from app.rag.embeddings import Embedder
from app.rag.retriever import BM25Retriever, Hit, RetrievalResult
from app.rag.vector_index import VectorIndex

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(branches: Sequence[Sequence[Hit]], *, k: int = 60) -> list[Hit]:
    if k < 1:
        raise ValueError("RRF k必须为正数")
    scores: dict[str, float] = {}
    for branch in branches:
        seen = set()
        for hit in branch:
            if hit.question_id in seen:
                continue
            seen.add(hit.question_id)
            scores[hit.question_id] = scores.get(hit.question_id, 0.0) + 1 / (k + len(seen))
    # dict插入顺序作为并列时的确定性顺序，BM25支路先插入。
    return sorted((Hit(qid, score) for qid, score in scores.items()), key=lambda h: -h.score)


class HybridRetriever:
    def __init__(self, lexical: BM25Retriever, embedder: Embedder, index: VectorIndex | None,
                 *, mode: str = "hybrid", rrf_k: int = 60, candidate_k: int = 20,
                 unavailable_reason: str | None = None, unavailable_version: str = "missing"):
        if mode not in ("hybrid", "vector") or rrf_k < 1 or candidate_k < 1:
            raise ValueError("检索策略非法")
        self._lexical, self._embedder, self._index = lexical, embedder, index
        self._mode, self._rrf_k, self._candidate_k = mode, rrf_k, candidate_k
        self._unavailable_reason = unavailable_reason or "index_missing"
        self.version = f"{mode}:{index.manifest['index_id'] if index else unavailable_version}:{rrf_k}:{candidate_k}"
        self._lock = threading.Lock()
        self._counts: Counter = Counter()

    def search(self, query: str, pool: Sequence[Question], limit: int) -> RetrievalResult:
        if limit < 1:
            raise ValueError("limit必须为正数")
        if not pool:
            return RetrievalResult((), self._mode, self._mode)
        count = max(limit, self._candidate_k)
        lexical = self._lexical.search(query, pool, count)
        try:
            if self._index is None:
                reason = self._unavailable_reason
                raise ValueError(reason)
            reason = "embedding_failed"
            vectors = self._embedder.embed([query])
            if len(vectors) != 1:
                raise ValueError("embedding_count_mismatch")
            reason = "vector_search_failed"
            vector = self._index.rank(vectors[0], pool, count)
            hits = reciprocal_rank_fusion([lexical.hits, vector], k=self._rrf_k) if self._mode == "hybrid" else vector
            with self._lock:
                self._counts["success"] += 1
            return RetrievalResult(tuple(hits[:limit]), self._mode, self._mode)
        except Exception as exc:
            with self._lock:
                self._counts["fallback"] += 1
                self._counts[f"reason:{reason}"] += 1
            logger.warning("retrieval_fallback mode=%s reason=%s category=%s",
                           self._mode, reason, type(exc).__name__)
            return RetrievalResult(lexical.hits[:limit], self._mode, "bm25", reason)

    def diagnostics(self) -> dict:
        with self._lock:
            counts = dict(self._counts)
        return {"requested": self._mode, "version": self.version,
                "embedding": self._embedder.spec.as_dict(), "semantic_model": self._embedder.spec.provider!='hash',
                "index_state": "ready" if self._index else self._unavailable_reason,
                "rrf_k": self._rrf_k, "candidate_k": self._candidate_k, "counts": counts,
                "embedding_usage": self._embedder.usage() if hasattr(self._embedder, 'usage') else {"network_calls": 0}}
