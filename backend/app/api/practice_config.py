"""Public role and practice capabilities, without answers or account data."""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.factories import load_assets
from app.practice_policy import practice_configuration
from app.schemas import InterviewCreateRequest
from app.agent.planner import HeuristicPlanner
from app.services.practice_planning import plan_practice

router = APIRouter(prefix='/api', tags=['practice'])


@router.get('/practice/config')
def practice_config():
    settings = get_settings()
    trees, bank = load_assets(settings)
    return practice_configuration([asdict(question) for question in bank],
                                  theme_limit=settings.max_plan_themes,
                                  names={key: tree.display_name for key, tree in trees.items()})


@router.post('/practice/preview')
def preview_practice(payload: InterviewCreateRequest):
    settings = get_settings()
    trees, bank = load_assets(settings)
    tree = trees.get(payload.position)
    if tree is None:
        raise HTTPException(404, '请选择可用的练习方向')
    if payload.resume_id:
        raise HTTPException(422, '预览仅使用岗位与主题，无需提交简历')
    try:
        plan = plan_practice(tree=tree, bank=bank, position=payload.position,
            difficulty=payload.difficulty, themes=payload.themes,
            duration_minutes=payload.duration_minutes, max_themes=settings.max_plan_themes,
            planner=HeuristicPlanner(tree))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return {'position': payload.position, 'duration_minutes': payload.duration_minutes,
            'themes': [{'name': item.theme, 'question_count': item.question_count} for item in plan],
            'main_question_count': sum(item.question_count for item in plan),
            'includes_coding': any(item.include_coding for item in plan),
            'note': ('追问另计；预计用时仅供参考。' if payload.themes is not None else
                     '追问另计。提交简历后会按经历调整主题；预计用时仅供参考。')}
