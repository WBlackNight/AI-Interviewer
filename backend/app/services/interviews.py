"""共享面试落库入口；可由调用方把来源关联纳入同一事务。"""
from app.repositories import create_interview
from app.schemas import InterviewCreateResponse, PlanItemOut
from app.security import issue_access
from app.services.accounts import attach_owner, lock_account


def save_interview(db, position, difficulty, plan, *, user_id=None, resume_id=None,
                   interview_id=None, account_id=None, commit=True):
    if account_id:
        lock_account(db, account_id)
    interview = create_interview(db, user_id=user_id, resume_id=resume_id, position=position,
        difficulty=difficulty, plan=plan, interview_id=interview_id, commit=False)
    token = None if account_id else issue_access(db, "interview", interview.id)
    if account_id:
        attach_owner(db, "interview", interview.id, account_id)
    if commit:
        db.commit()
    return InterviewCreateResponse(access_token=token, account_owned=account_id is not None,
        interview_id=interview.id, position=interview.position,
        plan=[PlanItemOut(**p.__dict__) for p in plan], ws_url=f"/ws/interview/{interview.id}")
