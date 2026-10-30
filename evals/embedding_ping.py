"""读取backend/.env，以一条合成查询验证Embedding；不打印密钥、正文或向量。"""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.rag.embeddings import EmbeddingError, build_embedder


def main():
    embedder = None
    try:
        embedder = build_embedder(Settings(_env_file=ROOT / "backend/.env"))
        vectors = embedder.embed(["数据库索引与范围查询"])
        result = {"result": "passed", "embedding": embedder.spec.as_dict(),
            "vector_count": len(vectors), "dimensions": len(vectors[0]),
            "normalized": math.isclose(math.hypot(*vectors[0]), 1, abs_tol=1e-6),
            "usage": embedder.usage() if hasattr(embedder, "usage") else {"network_calls": 0}}
        code = 0
    except Exception as exc:
        result = {"result": "failed", "error_category": type(exc).__name__,
            "reason": str(exc) if isinstance(exc, EmbeddingError) else "configuration_or_runtime_error",
            "usage": embedder.usage() if hasattr(embedder, "usage") else None}
        code = 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
