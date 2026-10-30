import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.domain import Question, ResumeData
from app.factories import load_assets
from app.rag.embeddings import EmbeddingError, HashEmbedder, normalize_vector
from app.rag.hybrid_retriever import HybridRetriever, reciprocal_rank_fusion
from app.rag.question_bank import QuestionBank
from app.rag.retriever import BM25Retriever, Hit, QuestionFilter, candidates
from app.rag.vector_index import IndexError, VectorIndex, build_index, digest
from tests.test_ws_recovery import api

ROOT = Path(__file__).resolve().parents[2]


def test_configured_index_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = Settings(_env_file=None, retrieval_index_path="data/retrieval/question_index.json")
    assert config.retrieval_index_path == ROOT / "data/retrieval/question_index.json"


def sample():
    return [Question("mysql", "java", "DB", "mid", "数据库索引B+树"),
            Question("txn", "java", "DB", "hard", "事务隔离快照MVCC"),
            Question("pool", "java", "Threads", "mid", "线程池队列拒绝策略"),
            Question("code", "java", "DB", "mid", "数组算法", is_coding=True),
            Question("other", "python", "DB", "mid", "数据库索引B+树")]


def configured(tmp_path, mode="hybrid"):
    questions, embedder = sample(), HashEmbedder(64)
    index, _ = build_index(tmp_path / "questions.json", questions, embedder)
    retriever = HybridRetriever(BM25Retriever(questions), embedder, index, mode=mode)
    return questions, embedder, index, retriever


def test_hash_vectors_are_stable_normalized_and_not_semantic():
    embedder = HashEmbedder(64)
    a, b = embedder.embed(["MYSQL 数据库", "mysql数据库"])
    assert a == b and a == HashEmbedder(64).embed(["mysql数据库"])[0]
    assert math.isclose(math.hypot(*a), 1, abs_tol=1e-12)
    assert embedder.spec.model == "char-ngram-hash-v1"


@pytest.mark.parametrize("values", [[0, 0], [True, 0], [float("nan"), 1], [float("inf"), 1], [1]])
def test_invalid_vectors_rejected(values):
    with pytest.raises(EmbeddingError):
        normalize_vector(values, 2)


def test_index_idempotence_does_not_reembed_or_rewrite(tmp_path):
    questions, embedder = sample(), HashEmbedder(64)
    path = tmp_path / "index.json"
    first, changed = build_index(path, questions, embedder)
    assert changed
    before = (path.stat().st_mtime_ns, path.read_bytes())
    class NoCalls:
        spec = embedder.spec
        def embed(self, texts): raise AssertionError("idempotent build must not embed")
    second, changed = build_index(path, questions, NoCalls())
    assert not changed and second.manifest == first.manifest
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before
    assert set(first.vectors) == {q.id for q in questions}


@pytest.mark.parametrize("change", ["question", "dimension", "revision", "model"])
def test_index_identity_rejects_same_dimension_model_or_corpus_changes(tmp_path, change):
    questions, embedder, index, _ = configured(tmp_path)
    spec = embedder.spec
    if change == "question": questions[0] = replace(questions[0], content="changed")
    if change == "dimension": spec = replace(spec, dimensions=32)
    if change == "revision": spec = replace(spec, revision="2")
    if change == "model": spec = replace(spec, model="other-model")
    with pytest.raises(IndexError, match="version_mismatch"):
        VectorIndex.load(tmp_path / "questions.json", questions, spec)


@pytest.mark.parametrize("change", ["checksum", "payload", "normalization", "duplicate", "nan"])
def test_corrupt_index_rejected(tmp_path, change):
    questions, embedder, _, _ = configured(tmp_path)
    path = tmp_path / "questions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if change == "checksum": data["rows"][0]["vector"][0] += .1
    if change == "payload": data["rows"][0]["payload"]["source"] = "wrong"
    if change == "normalization": data["rows"][0]["vector"] = [1.0] * 64
    if change == "duplicate": data["rows"][1] = data["rows"][0]
    if change == "nan": data["rows"][0]["vector"][0] = float("nan")
    if change not in ("checksum", "nan"):
        data["manifest"]["index_id"] = digest({"identity": data["manifest"]["identity"], "rows": data["rows"]})
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(IndexError): VectorIndex.load(path, questions, embedder.spec)


def test_failed_rebuild_preserves_previous_index(tmp_path):
    questions, embedder, _, _ = configured(tmp_path)
    path = tmp_path / "questions.json"
    before = path.read_bytes()
    class Bad:
        spec = embedder.spec
        def embed(self, texts): return [[0.0] * 64] * len(texts)
    with pytest.raises(EmbeddingError): build_index(path, questions, Bad(), rebuild=True)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_replace_failure_preserves_index_and_cleans_temp(tmp_path, monkeypatch):
    from app.rag import vector_index
    questions, embedder, _, _ = configured(tmp_path)
    path = tmp_path / "questions.json"
    before = path.read_bytes()
    def fail(*args): raise OSError("injected replace failure")
    monkeypatch.setattr(vector_index.os, "replace", fail)
    with pytest.raises(OSError, match="injected"):
        build_index(path, questions, embedder, rebuild=True)
    assert path.read_bytes() == before and not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("mode", ["bm25", "vector", "hybrid"])
def test_filters_apply_before_every_branch_and_no_repeat(tmp_path, mode):
    questions, embedder, index, retriever = configured(tmp_path, "hybrid" if mode == "bm25" else mode)
    bank = QuestionBank(questions, BM25Retriever(questions) if mode == "bm25" else retriever)
    filters = QuestionFilter(position="java", theme="DB", difficulty="mid")
    result = bank.search("数据库索引", filters)
    assert [h.question_id for h in result.hits] == ["mysql"]
    # exact mid已问后，仅放宽难度，不放宽主题、岗位、题型或已问约束。
    result = bank.search("索引", replace(filters, exclude=frozenset({"mysql"})))
    assert [h.question_id for h in result.hits] == ["txn"]
    assert not bank.search("索引", replace(filters, exclude=frozenset({"mysql", "txn"}))).hits
    assert not bank.search("索引", replace(filters, exclude=frozenset({"mysql"}), relax_difficulty=False)).hits
    assert bank.next_coding_question(position="java", exclude=set()).id == "code"
    assert bank.next_coding_question(position="java", exclude={"code"}) is None


def test_rrf_uses_ranks_deduplicates_and_has_stable_ties():
    a, b, c = Hit("a", 9999), Hit("b", -100), Hit("c", .001)
    result = reciprocal_rank_fusion([[a, a, b], [b, c]], k=60)
    assert [h.question_id for h in result] == ["b", "a", "c"]
    assert result[0].score == pytest.approx(1/62 + 1/61)
    assert result[1].score == pytest.approx(1/61)


def test_embedding_failure_falls_back_without_leaking_input_or_error(tmp_path, caplog):
    questions, embedder, index, _ = configured(tmp_path)
    class Broken:
        spec = embedder.spec
        def embed(self, texts): raise RuntimeError("synthetic-secret raw query")
    retriever = HybridRetriever(BM25Retriever(questions), Broken(), index)
    pool = candidates(questions, QuestionFilter("java", theme="DB"))
    result = retriever.search("synthetic-secret", pool, 3)
    assert result.actual == "bm25" and result.fallback_reason == "embedding_failed"
    assert "synthetic-secret" not in caplog.text
    assert retriever.diagnostics()["counts"]["fallback"] == 1


def test_empty_pool_never_embeds(tmp_path):
    _, embedder, index, _ = configured(tmp_path)
    class NoCalls:
        spec = embedder.spec
        def embed(self, texts): raise AssertionError("empty pool must not embed")
    result = HybridRetriever(BM25Retriever(sample()), NoCalls(), index).search("any", [], 1)
    assert not result.hits and not result.fallback_reason


def test_factory_never_builds_index_or_embeds_at_startup(tmp_path, monkeypatch):
    config = Settings(_env_file=None, retrieval_provider="hybrid", retrieval_index_path=tmp_path / "missing.json")
    def fail(*args): raise AssertionError("startup cannot embed")
    monkeypatch.setattr(HashEmbedder, "embed", fail)
    _, bank = load_assets(config)
    assert bank.diagnostics()["index_state"] == "index_missing"
    assert not config.retrieval_index_path.exists()
    # 规划仅检查可用候选，不触发召回/向量调用。
    from app.agent.planner import HeuristicPlanner
    trees, _ = load_assets(config)
    assert HeuristicPlanner(trees["java_backend"]).build_plan(position="java_backend",
        difficulty="mid", resume=ResumeData(), bank=bank, max_themes=3)
    assert bank.diagnostics()["counts"] == {}
    assert bank.next_question(position="java_backend", theme="MySQL", difficulty="mid", exclude=set())
    assert bank.diagnostics()["counts"]["fallback"] == 1


def test_factory_cache_reloads_after_explicit_index_creation(tmp_path):
    config = Settings(_env_file=None, retrieval_provider="hybrid", retrieval_index_path=tmp_path / "new.json")
    _, old = load_assets(config)
    build_index(config.retrieval_index_path, old.questions, HashEmbedder())
    _, new = load_assets(config)
    assert new is not old and new.diagnostics()["index_state"] == "ready"
    assert new.retrieval_version != old.retrieval_version


def test_query_pii_masked_before_either_branch(tmp_path):
    questions, embedder, index, _ = configured(tmp_path)
    seen = []
    class Recording:
        spec = embedder.spec
        def embed(self, texts):
            seen.extend(texts)
            return embedder.embed(texts)
    bank = QuestionBank(questions, HybridRetriever(BM25Retriever(questions), Recording(), index))
    bank.search("索引 13812345678 synthetic@example.com", QuestionFilter("java"))
    assert "13812345678" not in seen[0] and "synthetic@example.com" not in seen[0]


def test_metrics_known_ranking_and_eval_rejects_invalid_labels(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.retrieval_eval import metrics, evaluate
    result = metrics(["b", "c", "a"], {"a": 3, "b": 1}, 2)
    assert result["recall_at_k"] == .5 and result["mrr_at_k"] == 1
    assert result["ndcg_at_k"] == pytest.approx(1 / (7 + 1 / math.log2(3)))
    questions, embedder, index, _ = configured(tmp_path)
    invalid = [{"query_id":"one", "split":"smoke", "query":"SQL", "filters":{"position":"java"}, "relevance":{"other":3}}]
    with pytest.raises(ValueError, match="outside_candidates"):
        evaluate(QuestionBank(questions), index, embedder, invalid)


def test_evaluation_does_not_count_fallback_as_vector_success(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.retrieval_eval import evaluate
    questions, embedder, index, _ = configured(tmp_path)
    class Broken:
        spec = embedder.spec
        def embed(self, texts): raise RuntimeError("unavailable")
    records = [{"query_id":"one", "split":"smoke", "query":"SQL",
                "filters":{"position":"java"}, "relevance":{"mysql":3}}]
    with pytest.raises(ValueError, match="fell_back"):
        evaluate(QuestionBank(questions), index, Broken(), records)


def test_legacy_bm25_snapshot_without_retrieval_field_is_compatible():
    from app.agent.session import InterviewSession
    from app.agent.prober import SkillTreeProber
    from app.agent.scorer import HeuristicScorer
    from app.domain import PlanItem
    trees, bank = load_assets(Settings(_env_file=None))
    def session():
        return InterviewSession(interview_id="legacy", position="java_backend", bank=bank,
            scorer=HeuristicScorer(), prober=SkillTreeProber(trees["java_backend"]),
            plan=[PlanItem("MySQL",1.0,"mid",1,False)])
    first = session()
    first.start()
    legacy = first.snapshot()
    legacy.pop("retrieval_version")
    restored = session()
    restored.restore(legacy)
    assert restored.current_question == first.current_question


def test_api_hybrid_configuration_and_active_snapshot_freeze(api, tmp_path, monkeypatch):
    from app.api import routes, ws
    client, factory = api
    config = routes.settings.model_copy(update={"retrieval_provider":"hybrid", "retrieval_index_path":tmp_path / "real.json"})
    bank = QuestionBank.load(config.question_bank_dir)
    build_index(config.retrieval_index_path, bank.questions, HashEmbedder())
    monkeypatch.setattr(routes, "settings", config)
    monkeypatch.setattr(ws, "settings", config)
    diag = client.get("/api/diagnostics/retrieval").json()
    assert diag["requested"] == "hybrid" and diag["index_state"] == "ready" and not diag["semantic_model"]
    created = client.post("/api/interview", json={"position":"java_backend"}).json()
    path = "/ws/interview/" + created["interview_id"]
    with client.websocket_connect(path, subprotocols=["interview",created["access_token"]]) as socket:
        socket.send_json({"type":"start"})
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["current_question"]
    # 换策略不能悄悄改变进行中会话的后续选题。
    monkeypatch.setattr(ws, "settings", config.model_copy(update={"retrieval_rrf_k":61}))
    with client.websocket_connect(path, subprotocols=["interview",created["access_token"]]) as socket:
        socket.send_json({"type":"start"})
        assert socket.receive_json()["code"] == "assets_changed"
