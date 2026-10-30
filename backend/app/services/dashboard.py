"""本账户练习概览：有界摘要和北京时间日历统计，不读取回答、笔记正文或模型。"""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import case, func, select

from app.models.entities import Interview, ResourceOwner, RevisionTask, RevisionSchedule, RevisionNote
from app.services.history import summaries
from app.services.revision import revision_today
from app.services.preparation import plan_dashboard


def account_dashboard(db, account_id, skill_tree_dir):
    today = revision_today()
    days = [today - timedelta(days=6 - index) for index in range(7)]
    # 既有Interview结束时间为宿主本地的naive值，与history.summaries保持相同解释。
    # 将北京时间日界转回该存储时区再查询，不把本地时间误当UTC，也不改写旧数据。
    beijing = timezone(timedelta(hours=8))
    boundaries = [datetime.combine(day, time.min, tzinfo=beijing).astimezone().replace(tzinfo=None)
                  for day in days + [today + timedelta(days=1)]]
    ownership = ((ResourceOwner.resource_kind == 'interview') &
                 (ResourceOwner.resource_id == Interview.id) & (ResourceOwner.account_id == account_id))
    owned = select(Interview).join(ResourceOwner, ownership)
    counts = dict(db.execute(owned.with_only_columns(Interview.status, func.count()).group_by(Interview.status)).all())
    week = db.execute(select(*[func.count().filter(
        Interview.ended_at >= boundaries[index], Interview.ended_at < boundaries[index + 1])
        for index in range(7)]).select_from(Interview).join(ResourceOwner, ownership)
        .where(Interview.status == 'finished', Interview.ended_at >= boundaries[0], Interview.ended_at < boundaries[-1])).one()
    active = list(db.scalars(owned.where(Interview.status.in_(['created', 'running'])).order_by(
        case((Interview.status == 'running', 0), else_=1), ResourceOwner.created_at.desc(), Interview.id.desc()).limit(3)))
    recent = list(db.scalars(owned.where(Interview.status == 'finished').order_by(
        Interview.ended_at.desc().nullslast(), Interview.id.desc()).limit(3)))
    tasks = select(RevisionTask).where(RevisionTask.account_id == account_id)
    task_counts = dict(db.execute(tasks.with_only_columns(RevisionTask.status, func.count()).group_by(RevisionTask.status)).all())
    scheduled = tasks.add_columns(RevisionSchedule.due_date).outerjoin(RevisionSchedule, RevisionSchedule.task_id == RevisionTask.id)
    todo = scheduled.where(RevisionTask.status == 'todo')
    due = {name: db.scalar(select(func.count()).select_from(todo.where(condition).subquery())) for name, condition in {
        'today': RevisionSchedule.due_date == today, 'overdue': RevisionSchedule.due_date < today,
        'upcoming': RevisionSchedule.due_date > today, 'unscheduled': RevisionSchedule.due_date.is_(None)}.items()}
    priority = db.execute(todo.where(RevisionSchedule.due_date <= today).order_by(
        RevisionSchedule.due_date.asc(), RevisionTask.created_at.asc(), RevisionTask.id.asc()).limit(4)).all()
    note_count = db.scalar(select(func.count()).select_from(RevisionNote).join(RevisionTask,
        RevisionTask.id == RevisionNote.task_id).where(RevisionTask.account_id == account_id, RevisionNote.content != ''))
    return {
        'today': today.isoformat(), 'timezone': 'Asia/Shanghai',
        'interviews': {status: counts.get(status, 0) for status in ['created', 'running', 'finished', 'cancelled']},
        'tasks': {'todo': task_counts.get('todo', 0), 'done': task_counts.get('done', 0), **due},
        'notes_with_content': note_count,
        'preparation': plan_dashboard(db, account_id, today),
        'week': [{'date': day.isoformat(), 'finished': count} for day, count in zip(days, week)],
        'active': summaries(db, active, skill_tree_dir), 'recent': summaries(db, recent, skill_tree_dir),
        'priority_tasks': [{'id': task.id, 'interview_id': task.interview_id, 'position': task.position,
                            'theme': task.theme, 'due_date': day.isoformat()} for task, day in priority],
        'limits': {'active': 3, 'recent': 3, 'priority_tasks': 4},
        'note': '近七日按北京时间的完成日期计场数；任务状态由你手动维护，记录数量不代表能力提升。',
    }
