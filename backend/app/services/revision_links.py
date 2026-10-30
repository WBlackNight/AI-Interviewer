"""复习来源与最新练习摘要；只读关联字段，不读取回答。"""
from sqlalchemy import func, select
from app.models.entities import Interview, RevisionPractice, RevisionTask


def latest_practices(db, task_ids):
    if not task_ids:
        return {}
    latest = select(func.max(RevisionPractice.id)).where(
        RevisionPractice.task_id.in_(task_ids)).group_by(RevisionPractice.task_id)
    return {task_id: {"interview_id": interview_id, "status": status}
            for task_id, interview_id, status in db.execute(select(
                RevisionPractice.task_id, Interview.id, Interview.status).join(
                    Interview, Interview.id == RevisionPractice.interview_id).where(RevisionPractice.id.in_(latest)))}


def revision_source(db, interview_id):
    row = db.execute(select(RevisionTask.id, RevisionTask.interview_id, RevisionTask.theme).join(
        RevisionPractice, RevisionPractice.task_id == RevisionTask.id).where(
            RevisionPractice.interview_id == interview_id)).first()
    return {"task_id": row.id, "interview_id": row.interview_id, "theme": row.theme} if row else None
