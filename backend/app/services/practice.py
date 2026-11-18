"""专项大纲只使用当前岗位可出题的知识主题，不调用模型规划。"""
from dataclasses import replace

from app.domain import PlanItem
from app.agent.skill_tree import SkillTree
from app.rag.question_bank import QuestionBank
from app.rag.retriever import QuestionFilter
from app.practice_policy import DURATION_QUESTIONS


def timed_plan(plan: list[PlanItem], bank: QuestionBank, position: str,
               duration_minutes: int | None) -> list[PlanItem]:
    if duration_minutes is not None and duration_minutes not in DURATION_QUESTIONS:
        raise ValueError('请选择5、10或15分钟的练习')
    capacities = [len(bank.available(QuestionFilter(position=position, theme=item.theme, is_coding=False)))
                  for item in plan]
    if duration_minutes is None:
        sized = [replace(item, question_count=min(item.question_count, capacity))
                 for item, capacity in zip(plan, capacities) if capacity]
        return _normalize_weights(sized)
    remaining = DURATION_QUESTIONS[duration_minutes]
    counts = [0] * len(plan)
    for _ in range(remaining):
        available = [index for index, capacity in enumerate(capacities) if counts[index] < capacity]
        if not available:
            break
        # Cover themes first, then allocate remaining questions in proportion to plan weights.
        index = min(available, key=lambda index: counts[index] / max(plan[index].weight, .000001))
        counts[index] += 1
    sized = [replace(item, question_count=count, include_coding=False)
             for item, count in zip(plan, counts) if count]
    return _normalize_weights(sized)


def _normalize_weights(plan):
    total = sum(item.weight for item in plan)
    return [replace(item, weight=item.weight / total if total else 1 / len(plan)) for item in plan]


def available_themes(tree: SkillTree, bank: QuestionBank, position: str) -> list[str]:
    return [theme for theme in tree.root_names()
            if bank.available(QuestionFilter(position=position, theme=theme))]


def practice_plan(tree: SkillTree, bank: QuestionBank, position: str, difficulty: str,
                  themes: list[str], limit: int) -> list[PlanItem]:
    if not themes or len(themes) > limit or len(set(themes)) != len(themes):
        raise ValueError(f"请选择1至{limit}个不重复的知识主题")
    allowed = available_themes(tree, bank, position)
    if any(theme not in allowed for theme in themes):
        raise ValueError("所选主题不属于当前岗位的可用知识主题")
    return [PlanItem(theme=theme, weight=1 / len(themes), difficulty=difficulty,
                     question_count=min(2, len(bank.available(QuestionFilter(
                         position=position, theme=theme)))), include_coding=False)
            for theme in themes]


def weak_practice_themes(report: dict, tree: SkillTree | None, bank: QuestionBank, limit: int) -> list[str]:
    if not report["is_complete"] or tree is None:
        return []
    allowed = available_themes(tree, bank, report["position"])
    return [theme for theme in report["weak_points"] if theme in allowed][:limit]
