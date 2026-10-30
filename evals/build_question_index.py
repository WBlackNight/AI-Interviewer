"""独立构建题库向量索引；相同题库/模型/参数重复运行不重新embedding。

python evals/build_question_index.py
python evals/build_question_index.py --dimensions 256 --output data/retrieval/question_index.json
题库/维度/模型变化时须使用新路径或显式--rebuild。hash离线，zhipu会调用远程API。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.rag.embeddings import build_embedder
from app.rag.question_bank import QuestionBank
from app.rag.vector_index import build_index


def main():
    config = Settings(_env_file=ROOT / "backend" / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-dir", type=Path, default=config.question_bank_dir)
    parser.add_argument("--output", type=Path, default=config.retrieval_index_path)
    parser.add_argument("--dimensions", type=int, default=config.embedding_dimensions)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    try:
        bank = QuestionBank.load(args.bank_dir)
        embedder=build_embedder(config.model_copy(update={'embedding_dimensions':args.dimensions}))
        index, changed = build_index(args.output, bank.questions, embedder,
                                     rebuild=args.rebuild)
        print(json.dumps({"status": "built" if changed else "unchanged", **index.manifest,
                          "semantic_model": embedder.spec.provider!='hash',
                          "usage":embedder.usage() if hasattr(embedder,'usage') else {'network_calls':0}}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # 不输出原始异常正文，避免路径/原文件数据进入日志。
        print(json.dumps({"status": "failed", "error_category": type(exc).__name__,
            "hint": "检查题库与维度；版本变更请选新索引路径或显式--rebuild"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
