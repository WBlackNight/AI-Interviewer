"""Bounded account-owned export, independent of HTTP route definitions."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import (
    PreparationGoal, PreparationPlan, QuestionMark, RevisionTask, RevisionNote, RevisionSchedule,
)

MAX_EXPORT_ROWS = 1000


def export_revision_data(db, account_id):
    def bounded(statement):
        rows = list(db.execute(statement.limit(MAX_EXPORT_ROWS + 1)))
        if len(rows) > MAX_EXPORT_ROWS:
            raise HTTPException(413, '数据量超过单次导出上限，请联系管理员备份数据库')
        return rows
    tasks = bounded(
        select(RevisionTask, RevisionNote, RevisionSchedule)
        .outerjoin(RevisionNote,RevisionNote.task_id==RevisionTask.id)
        .outerjoin(RevisionSchedule,RevisionSchedule.task_id==RevisionTask.id)
        .where(RevisionTask.account_id == account_id).order_by(RevisionTask.id)
    )
    marks = bounded(
        select(QuestionMark).where(QuestionMark.account_id == account_id).order_by(QuestionMark.id)
    )
    plans = bounded(
        select(PreparationPlan).where(PreparationPlan.account_id == account_id).order_by(PreparationPlan.id)
    )
    goals = {
        goal.plan_id: goal.target_sessions
        for goal in db.scalars(
            select(PreparationGoal)
            .join(PreparationPlan, PreparationPlan.id == PreparationGoal.plan_id)
            .where(PreparationPlan.account_id == account_id)
        )
    }
    return {
        'format_version': 1,
        'scope': 'revision_data',
        'tasks': [
            {
                'id': task.id,
                'interview_id': task.interview_id,
                'position': task.position,
                'theme': task.theme,
                'status': task.status,
                'focus_points': task.focus_points,
                'created_at': task.created_at,
                'completed_at': task.completed_at,
                'due_date': schedule.due_date if schedule else None,
                'note': note.content if note else '',
                'note_updated_at': note.updated_at if note else None,
            }
            for task, note, schedule in tasks
        ],
        'question_marks': [
            {
                'position': mark.position,
                'question_id': mark.question_id,
                'status': mark.status,
                'created_at': mark.created_at,
                'reviewed_at': mark.reviewed_at,
            }
            for (mark,) in marks
        ],
        'plans': [
            {
                'name': plan.name,
                'position': plan.position,
                'themes': plan.themes,
                'difficulty': plan.difficulty,
                'target_date': plan.target_date,
                'target_sessions': goals.get(plan.id),
                'status': plan.status,
                'created_at': plan.created_at,
                'updated_at': plan.updated_at,
            }
            for (plan,) in plans
        ],
    }

