"""题库与检索（RAG 子系统的召回端）。

- 数据：data/question_bank/<position>.jsonl，一题一行（题目天然是检索单元，不做切块）；
- 检索：主题/难度硬过滤 + BM25 软排序 + 已问排除；
- 默认BM25；工厂可装配离线向量或RRF混合检索，所有支路共享候选过滤。

启发式实现完全确定性（无网络依赖），保证测试与离线演示稳定。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.domain import Question
from app.rag.retriever import BM25Retriever, QuestionFilter, Retriever, RetrievalResult, candidates
from app.security import sanitize_pii


class QuestionBank:
    def __init__(self, questions: Iterable[Question], retriever: Retriever | None = None):
        self._questions: list[Question] = list(questions)
        self._by_id: dict[str, Question] = {q.id: q for q in self._questions}
        if len(self._by_id) != len(self._questions):
            raise ValueError("题目 ID 必须唯一")
        self._retriever = retriever or BM25Retriever(self._questions)

    @property
    def retrieval_version(self) -> str:
        return self._retriever.version

    def diagnostics(self) -> dict:
        return self._retriever.diagnostics()

    def available(self, filters: QuestionFilter) -> list[Question]:
        return candidates(self._questions, filters)

    def search(self, query: str, filters: QuestionFilter, *, top_k: int = 3) -> RetrievalResult:
        if not 1 <= top_k <= 1000 or len(query) > 2000:
            raise ValueError("检索数量或查询长度非法")
        pool = self.available(filters)
        return self._retriever.search(sanitize_pii(query), pool, top_k)

    # ------------------------------------------------------------- 查询

    def get(self, question_id: str) -> Question | None:
        return self._by_id.get(question_id)

    def __len__(self) -> int:
        return len(self._questions)

    def __iter__(self):
        return iter(self._questions)

    @property
    def questions(self) -> list[Question]:
        return list(self._questions)

    def has_coding(self, position: str) -> bool:
        return any(q.is_coding for q in self._questions if q.position == position)

    def next_question(
        self,
        *,
        position: str,
        theme: str,
        difficulty: str,
        exclude: set[str],
        is_coding: bool = False,
    ) -> Question | None:
        """统一过滤后由配置的召回器排序，不重复已问题。

        放宽策略（逐级）：
        1. 主题 + 难度 + 未问
        2. 主题 + 未问（难度放宽）
        3. 未问候选耗尽则返回None，不放宽岗位、主题、题型或已问约束。
        """
        result = self.search(f"{theme} {difficulty}", QuestionFilter(position=position,
            theme=theme, difficulty=difficulty, exclude=frozenset(exclude), is_coding=is_coding), top_k=1)
        return self.get(result.hits[0].question_id) if result.hits else None

    def next_coding_question(self, *, position: str, exclude: set[str]) -> Question | None:
        result = self.search("编程 算法", QuestionFilter(position=position, is_coding=True,
            exclude=frozenset(exclude)), top_k=1)
        return self.get(result.hits[0].question_id) if result.hits else None

    # ------------------------------------------------------------- 加载

    @classmethod
    def load(cls, question_bank_dir: Path) -> "QuestionBank":
        import json

        questions: list[Question] = []
        for path in sorted(question_bank_dir.glob("*.jsonl")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    questions.append(Question.from_dict(json.loads(line)))
                except (KeyError, ValueError) as exc:  # 数据缺陷 fail-fast
                    raise ValueError(f"{path.name}:{line_no} 题目格式非法: {exc}") from exc
        return cls(questions)
