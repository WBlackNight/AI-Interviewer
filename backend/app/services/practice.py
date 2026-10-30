"""专项大纲只使用当前岗位可出题的知识主题，不调用模型规划。"""
from app.domain import PlanItem
from app.agent.skill_tree import SkillTree
from app.rag.question_bank import QuestionBank
from app.rag.retriever import QuestionFilter


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
