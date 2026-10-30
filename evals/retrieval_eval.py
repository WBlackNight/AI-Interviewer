"""固定smoke查询的BM25/配置的向量/RRF对照。不是独立质量评估或显著性证据。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.rag.embeddings import Embedder, build_embedder
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.question_bank import QuestionBank
from app.rag.retriever import BM25Retriever, QuestionFilter
from app.rag.vector_index import VectorIndex, corpus_version


def metrics(ranked: list[str], relevance: dict[str, int], k: int) -> dict:
    if k < 1 or len(set(ranked)) != len(ranked) or not relevance:
        raise ValueError("invalid_rank_or_relevance")
    relevant = {qid for qid, grade in relevance.items() if grade > 0}
    if not relevant:
        raise ValueError("no_positive_relevance")
    top = ranked[:k]
    recall = len(set(top) & relevant) / len(relevant)
    rr = next((1.0 / rank for rank, qid in enumerate(top, 1) if qid in relevant), 0.0)
    dcg = sum((2 ** relevance.get(qid, 0) - 1) / math.log2(rank + 1)
              for rank, qid in enumerate(top, 1))
    ideal = sum((2 ** grade - 1) / math.log2(rank + 1)
                for rank, grade in enumerate(sorted(relevance.values(), reverse=True)[:k], 1))
    return {"recall_at_k": recall, "ndcg_at_k": dcg / ideal, "mrr_at_k": rr}


def percentile95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)]


def evaluate(bank: QuestionBank, index: VectorIndex, embedder: Embedder,
             records: list[dict], *, k: int = 3, rrf_k: int = 60, candidate_k: int = 20) -> dict:
    if not records or not 1 <= k <= 1000:
        raise ValueError("invalid_eval_parameters")
    lexical = BM25Retriever(bank.questions)
    strategies = {"bm25": lexical,
        "vector": HybridRetriever(lexical, embedder, index, mode="vector", candidate_k=candidate_k),
        "hybrid": HybridRetriever(lexical, embedder, index, rrf_k=rrf_k, candidate_k=candidate_k)}
    banks = {name: QuestionBank(bank.questions, retriever) for name, retriever in strategies.items()}
    seen = set()
    by_strategy = {name: [] for name in strategies}
    for record in records:
        qid = record["query_id"]
        if qid in seen or record.get("split") != "smoke":
            raise ValueError("duplicate_id_or_non_smoke_split")
        seen.add(qid)
        filters = dict(record["filters"])
        filters["exclude"] = frozenset(filters.get("exclude", []))
        constraint = QuestionFilter(**filters)
        pool = bank.available(constraint)
        allowed = {q.id for q in pool}
        relevance = record["relevance"]
        if (not relevance or any(q not in allowed for q in relevance)
                or any(type(v) is not int or not 0 <= v <= 3 for v in relevance.values())):
            raise ValueError("relevance_outside_candidates_or_invalid_grade")
        for name, selected in banks.items():
            start = time.perf_counter()
            result = selected.search(record["query"], constraint, top_k=k)
            elapsed = (time.perf_counter() - start) * 1000
            if result.actual != name or result.fallback_reason:
                raise ValueError("evaluation_fell_back_not_a_vector_result")
            ranked = [hit.question_id for hit in result.hits]
            if set(ranked) - allowed:
                raise ValueError("filter_violation")
            by_strategy[name].append({"query_id": qid, "candidate_count": len(pool),
                "ranked_ids": ranked, **metrics(ranked, relevance, k), "latency_ms": elapsed})
    summaries = {}
    for name, rows in by_strategy.items():
        elapsed = [r["latency_ms"] for r in rows]
        summaries[name] = {**{metric: statistics.mean(r[metric] for r in rows)
            for metric in ("recall_at_k", "ndcg_at_k", "mrr_at_k")},
            "latency_p50_ms": statistics.median(elapsed), "latency_p95_ms": percentile95(elapsed),
            "fallback_count": 0, "per_query": rows}
    return {"split": "smoke", "independent_blind_labels": False, "query_count": len(records),
        "k": k, "rrf_k": rrf_k, "candidate_k": candidate_k,
        "embedding": embedder.spec.as_dict(), "semantic_model": embedder.spec.provider!='hash',
        "corpus_sha256": corpus_version(bank.questions), "index_id": index.manifest["index_id"],
        "cost": embedder.usage() if hasattr(embedder,'usage') else {"network_calls":0,"currency_cost":None},
        "interpretation": "开发者编写的小型smoke集，仅验证链路；不得据此声称语义质量或显著优于BM25；向量与混合分别编码查询，延迟包含API时间",
        "strategies": summaries}


def main():
    config = Settings(_env_file=ROOT / "backend" / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-dir", type=Path, default=config.question_bank_dir)
    parser.add_argument("--index-path", type=Path, default=config.retrieval_index_path)
    parser.add_argument("--queries", type=Path, default=ROOT / "data/evals/retrieval_smoke.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dimensions", type=int, default=config.embedding_dimensions)
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    try:
        raw = args.queries.read_bytes()
        records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        bank=QuestionBank.load(args.bank_dir)
        embedder=build_embedder(config.model_copy(update={'embedding_dimensions':args.dimensions}))
        index = VectorIndex.load(args.index_path, bank.questions, embedder.spec)
        result = evaluate(bank, index, embedder, records, k=args.k,
            rrf_k=config.retrieval_rrf_k, candidate_k=config.retrieval_candidate_k)
        result["queries_sha256"] = hashlib.sha256(raw).hexdigest()
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        if args.output:
            summary = {key: value for key, value in result.items() if key != "strategies"}
            summary["strategies"] = {name: {key: value for key, value in row.items() if key != "per_query"}
                                     for name, row in result["strategies"].items()}
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(encoded)
        return 0
    except Exception as exc:
        print(json.dumps({"result": "failed", "error_category": type(exc).__name__,
                          "note": "检查索引版本、查询标注和过滤；发生回退不能视为向量评测通过"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
