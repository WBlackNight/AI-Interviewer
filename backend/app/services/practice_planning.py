"""One planning boundary for previews and persisted practice sessions.

The caller owns model lifetime, budget and persistence. This module only turns
validated intent and an injected planner into a capacity-bounded plan.
"""
from app.domain import ResumeData
from app.services.practice import practice_plan, timed_plan


def plan_practice(*, tree, bank, position, difficulty, themes=None,
                  duration_minutes=None, max_themes=3, resume=None, planner=None):
    if themes is not None:
        plan = practice_plan(tree, bank, position, difficulty, themes, max_themes)
    else:
        if planner is None:
            raise ValueError('综合练习需要可用的规划器')
        plan = planner.build_plan(position=position, difficulty=difficulty,
                                  resume=resume or ResumeData(), bank=bank,
                                  max_themes=max_themes)
    plan = timed_plan(plan, bank, position, duration_minutes)
    if not plan:
        raise ValueError('当前配置没有可用题目，请更换岗位或主题')
    return plan
