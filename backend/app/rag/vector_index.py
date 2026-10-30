"""离线JSON向量索引：版本、题库/模型/向量校验与原子替换。仅适合小型题库。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from app.domain import Question
from app.rag.embeddings import Embedder, EmbeddingSpec, normalize_vector
from app.rag.retriever import Hit, document_text

MAX_INDEX_BYTES = 32 * 1024 * 1024


class IndexError(ValueError):
    """安全错误代码，不含文件正文/凭据。"""


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def question_version(q: Question) -> str:
    return digest(asdict(q))


def corpus_version(questions: Sequence[Question]) -> str:
    return digest([(q.id, question_version(q)) for q in sorted(questions, key=lambda q: q.id)])


def identity(questions: Sequence[Question], spec: EmbeddingSpec) -> dict:
    return {"format": 1, "document_version": "theme-content-v1", "embedding": spec.as_dict(),
            "corpus_sha256": corpus_version(questions), "question_count": len(questions)}


def payload(q: Question) -> dict:
    return {"question_id": q.id, "source": q.source, "position": q.position,
            "theme": q.theme, "difficulty": q.difficulty, "is_coding": q.is_coding,
            "question_version": question_version(q)}


@dataclass(frozen=True)
class VectorIndex:
    manifest: dict
    vectors: dict[str, tuple[float, ...]]

    @classmethod
    def load(cls, path: Path, questions: Sequence[Question], spec: EmbeddingSpec) -> "VectorIndex":
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_INDEX_BYTES + 1)
            if len(raw) > MAX_INDEX_BYTES:
                raise IndexError("index_too_large")
            data = json.loads(raw)
            manifest, rows = data["manifest"], data["rows"]
            expected = identity(questions, spec)
            if manifest.get("identity") != expected:
                raise IndexError("index_version_mismatch")
            if not isinstance(rows, list) or len(rows) != len(questions):
                raise IndexError("index_rows_mismatch")
            if manifest.get("index_id") != digest({"identity": expected, "rows": rows}):
                raise IndexError("index_checksum_mismatch")
            by_id = {q.id: q for q in questions}
            vectors = {}
            for row in rows:
                qid = row["payload"]["question_id"]
                if qid not in by_id or qid in vectors or row["payload"] != payload(by_id[qid]):
                    raise IndexError("index_payload_mismatch")
                values = row["vector"]
                # 验证规范化，不能悄悄修复损坏的持久化数据。
                normalized = normalize_vector(values, spec.dimensions)
                if any(abs(a - b) > 1e-6 for a, b in zip(values, normalized)):
                    raise IndexError("index_not_normalized")
                vectors[qid] = tuple(values)
            return cls(manifest, vectors)
        except IndexError:
            raise
        except FileNotFoundError:
            raise IndexError("index_missing") from None
        except Exception:
            raise IndexError("index_invalid") from None

    def rank(self, query_vector: Sequence[float], pool: Sequence[Question], limit: int) -> list[Hit]:
        dimensions = self.manifest["identity"]["embedding"]["dimensions"]
        vector = normalize_vector(query_vector, dimensions)
        if any(q.id not in self.vectors for q in pool):
            raise IndexError("candidate_missing")
        # 只在统一过滤后的候选池内计算，已问/其他岗位/题型不会占满top-k。
        hits = [Hit(q.id, sum(a * b for a, b in zip(vector, self.vectors[q.id]))) for q in pool]
        return sorted(hits, key=lambda h: -h.score)[:limit]


def build_index(path: Path, questions: Sequence[Question], embedder: Embedder, *,
                rebuild: bool = False, batch_size: int = 32) -> tuple[VectorIndex, bool]:
    if not questions or len({q.id for q in questions}) != len(questions) or batch_size < 1:
        raise IndexError("invalid_corpus_or_batch")
    if path.exists() and not rebuild:
        # 完整验证已有索引后复用，不重复embedding，不修改mtime。
        return VectorIndex.load(path, questions, embedder.spec), False
    rows = []
    for start in range(0, len(questions), batch_size):
        batch = questions[start:start + batch_size]
        vectors = embedder.embed([document_text(q) for q in batch])
        if len(vectors) != len(batch):
            raise IndexError("embedding_count_mismatch")
        rows.extend({"payload": payload(q), "vector": normalize_vector(v, embedder.spec.dimensions)}
                    for q, v in zip(batch, vectors))
    info = identity(questions, embedder.spec)
    manifest = {"identity": info, "index_id": digest({"identity": info, "rows": rows})}
    encoded = json.dumps({"manifest": manifest, "rows": rows}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INDEX_BYTES:
        raise IndexError("index_too_large")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return VectorIndex.load(path, questions, embedder.spec), True
