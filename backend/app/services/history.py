"""批量构建摘要，只读取数据库与技能树，不加载向量模型。"""
from datetime import timezone
from sqlalchemy import select, func
from app.agent.skill_tree import load_skill_tree
from app.models.entities import Interview, InterviewEvent, QuestionScore, ResourceOwner


def account_history(db, account_id, skill_tree_dir, *, offset=0, limit=20, status=None, position=None, difficulty=None):
    """归属范围先于筛选和计数，保留原归属时间/ID排序。"""
    owned = select(Interview).join(ResourceOwner,
        (ResourceOwner.resource_id == Interview.id) & (ResourceOwner.resource_kind == 'interview')).where(
            ResourceOwner.account_id == account_id)
    positions = list(db.scalars(owned.with_only_columns(Interview.position).distinct().order_by(Interview.position)))
    if position is not None:
        owned = owned.where(Interview.position == position)
    if difficulty is not None:
        owned = owned.where(Interview.difficulty == difficulty)
    counts = dict(db.execute(owned.with_only_columns(Interview.status, func.count()).group_by(Interview.status)).all())
    if status is not None:
        owned = owned.where(Interview.status == status)
    total = db.scalar(select(func.count()).select_from(owned.subquery()))
    rows = list(db.scalars(owned.order_by(ResourceOwner.created_at.desc(), Interview.id.desc()).offset(offset).limit(limit)))
    trees = load_skill_tree(skill_tree_dir)
    return {'items': summaries(db, rows, skill_tree_dir), 'total': total, 'offset': offset, 'limit': limit,
            'has_more': offset + len(rows) < total, 'status': status, 'position': position, 'difficulty': difficulty,
            'status_counts': {key: counts.get(key, 0) for key in ('created', 'running', 'finished', 'cancelled')},
            'positions': [{'id': key, 'display_name': trees[key].display_name if key in trees else key} for key in positions]}


def summaries(db, interviews, skill_tree_dir):
    ids = [i.id for i in interviews]
    if not ids:
        return []
    counts = dict(db.execute(select(QuestionScore.interview_id, func.count()).where(
        QuestionScore.interview_id.in_(ids)).group_by(QuestionScore.interview_id)).all())
    activity = dict(db.execute(select(InterviewEvent.interview_id, func.max(InterviewEvent.created_at)).where(
        InterviewEvent.interview_id.in_(ids)).group_by(InterviewEvent.interview_id)).all())
    trees = load_skill_tree(skill_tree_dir)
    def stamp(value, utc=False):
        if value is None:
            return None
        aware = value.replace(tzinfo=timezone.utc) if utc else value.astimezone()
        return aware.astimezone(timezone.utc).isoformat()
    return [{"interview_id": i.id, "position": i.position,
             "position_display_name": trees[i.position].display_name if i.position in trees else i.position,
             "difficulty": i.difficulty, "status": i.status, "theme_count": len(i.plan),
             "answer_count": counts.get(i.id, 0), "started_at": stamp(i.started_at),
             "ended_at": stamp(i.ended_at), "last_activity_at": stamp(i.ended_at)
                 or stamp(activity.get(i.id), True) or stamp(i.started_at)} for i in interviews]
