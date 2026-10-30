"""仓储层：ORM ↔ domain 转换与持久化的唯一入口。"""
from __future__ import annotations
from dataclasses import asdict

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain import PlanItem, Question, ScoreRecord
from app.models.entities import (
    Interview,
    InterviewEvent,
    Question as QuestionORM,
    QuestionScore,
    Resume,
    User,
    InterviewRuntime, InterviewSubmission, TurnMetadata, ScoreOriginRecord,
)


# ---------------------------------------------------------------- 题库


def seed_questions(db: Session, questions: list[Question]) -> int:
    """幂等入库题库（按主键 upsert）。返回新增条数。"""
    added = 0
    for q in questions:
        existing = db.get(QuestionORM, q.id)
        values = dict(
                id=q.id,
                position=q.position,
                theme=q.theme,
                difficulty=q.difficulty,
                content=q.content,
                answer_points=[
                    {"point": p.point, "keywords": list(p.keywords)}
                    for p in q.answer_points
                ],
                is_coding=q.is_coding,
                testcases=[{"input": t.input, "expected": t.expected} for t in q.testcases],
                source=q.source,
            )
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(QuestionORM(**values))
            added += 1
    db.commit()
    return added


# ---------------------------------------------------------------- 用户/简历


def create_user_with_resume(db: Session, *, name: str, resume_text: str, structured: dict,
                            commit: bool = True, resume_id: str | None = None) -> Resume:
    user = User(name=name or "匿名用户")
    db.add(user)
    db.flush()
    resume = Resume(
        user_id=user.id,
        raw_text=resume_text,
        structured=structured,
    )
    if resume_id:
        resume.id = resume_id
    db.add(resume)
    if commit:
        db.commit()
    else:
        db.flush()
    return resume


# ---------------------------------------------------------------- 面试


def create_interview(
    db: Session,
    *,
    user_id: str | None,
    resume_id: str | None,
    position: str,
    difficulty: str,
    plan: list[PlanItem],
    interview_id: str | None = None,
    commit: bool = True,
) -> Interview:
    interview = Interview(
        user_id=user_id,
        resume_id=resume_id,
        position=position,
        difficulty=difficulty,
        plan=[
            {
                "theme": p.theme,
                "weight": p.weight,
                "difficulty": p.difficulty,
                "question_count": p.question_count,
                "include_coding": p.include_coding,
            }
            for p in plan
        ],
        status="created",
    )
    if interview_id:
        interview.id = interview_id
    db.add(interview)
    db.flush()
    db.add(InterviewRuntime(interview_id=interview.id))
    if commit:
        db.commit()
    return interview


def get_interview(db: Session, interview_id: str) -> Interview | None:
    return db.get(Interview, interview_id)


def get_resume(db: Session, resume_id: str) -> Resume | None:
    return db.get(Resume, resume_id)



def save_score_records(db: Session, interview_id: str, records: list[ScoreRecord], *, commit: bool = True) -> None:
    for record in records:
        score = QuestionScore(
                interview_id=interview_id,
                question_id=record.question_id,
                theme=record.theme,
                content=record.content,
                score=record.result.score,
                dimensions=record.result.dimensions,
                evidence=record.result.evidence,
                key_points_hit=list(record.result.key_points_hit),
                key_points_missed=list(record.result.key_points_missed),
                sandbox=record.result.sandbox,
                probe_depth=record.probe_depth,
                answer_text=record.answer_text,
            )
        db.add(score)
        db.flush()
        db.add(ScoreOriginRecord(score_id=score.id, data={
            **asdict(record.result.origin), "question_version": record.question_version,
            "main_question_id": record.main_question_id or record.question_id.split("#p")[0],
            "main_question_version": record.main_question_version,
            "question_difficulty": record.question_difficulty, "is_coding": record.is_coding,
        }))
        if record.turn_id:
            db.add(TurnMetadata(score_id=score.id, turn_id=record.turn_id,
                                main_question_id=record.main_question_id,
                                skill_node_id=record.skill_node_id))
    if commit:
        db.commit()


class ConcurrentTurnError(ValueError):
    pass


def cancel_interview(db: Session, interview: Interview) -> tuple[bool, int]:
    """独立终态，不依赖资产或Agent；提升版本使在途轮次不能提交。"""
    runtime = db.get(InterviewRuntime, interview.id)
    version = runtime.version if runtime else 0
    if interview.status == "cancelled":
        return False, version
    if interview.status not in ("created", "running"):
        raise ValueError("当前面试不能取消")
    last_seq = db.scalar(select(func.max(InterviewEvent.seq)).where(InterviewEvent.interview_id == interview.id))
    seq = runtime.next_seq if runtime else ((last_seq if last_seq is not None else -1) + 1)
    previous_snapshot = runtime.snapshot if runtime and isinstance(runtime.snapshot, dict) else {}
    snapshot = {**previous_snapshot, "finished": True, "cancelled": True,
                "state": "finished", "current": None, "scoring_target": None, "question_event": None}
    if runtime:
        updated = db.execute(update(InterviewRuntime).where(InterviewRuntime.interview_id == interview.id,
            InterviewRuntime.version == version, InterviewRuntime.next_seq == seq).values(
                version=version + 1, next_seq=seq + 1, snapshot=snapshot),
            execution_options={"synchronize_session": False})
        if updated.rowcount != 1:
            raise ConcurrentTurnError("面试已更新，请重试取消")
    else:
        db.add(InterviewRuntime(interview_id=interview.id, version=version + 1,
                                next_seq=seq + 1, snapshot=snapshot))
    updated = db.execute(update(Interview).where(Interview.id == interview.id,
        Interview.status.in_(["created", "running"])).values(status="cancelled", ended_at=datetime.now()),
        execution_options={"synchronize_session": False})
    if updated.rowcount != 1:
        raise ConcurrentTurnError("面试已结束或更新，请刷新")
    db.add(InterviewEvent(interview_id=interview.id, seq=seq, type="interview_cancelled", payload={
        "type": "interview_cancelled", "text": "面试已取消，已提交回答保留为部分报告。",
        "seq": seq, "version": version + 1}))
    db.commit()
    db.expire_all()
    return True, version + 1


def cancelled_snapshot(db: Session, interview_id: str) -> list[dict]:
    runtime = db.get(InterviewRuntime, interview_id)
    return [{"type": "snapshot", "state": "cancelled", "finished": True, "cancelled": True,
             "version": runtime.version if runtime else 0, "current_question": None,
             "events": [event.payload for event in load_events(db, interview_id)]}]


def commit_turn(db: Session, interview_id: str, version: int, snapshot: dict,
                events: list[dict], records: list[ScoreRecord],
                message_id: str | None = None, request_hash: str | None = None) -> list[dict]:
    interview = db.get(Interview, interview_id)
    if interview is None or interview.status == "cancelled":
        raise ConcurrentTurnError("面试已取消或删除，不能继续提交")
    runtime = db.get(InterviewRuntime, interview_id)
    if runtime is None:
        raise ConcurrentTurnError("会话没有可恢复快照，请创建新面试")
    seq = runtime.next_seq
    result = db.execute(update(InterviewRuntime).where(
        InterviewRuntime.interview_id == interview_id, InterviewRuntime.version == version,
    ).values(version=version + 1, next_seq=seq + len(events), snapshot=snapshot),
        execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        raise ConcurrentTurnError("会话已更新，请同步后再提交")
    numbered = [{**e, "seq": seq + i, "version": version + 1} for i, e in enumerate(events)]
    for event in numbered:
        db.add(InterviewEvent(interview_id=interview_id, seq=event["seq"],
                              type=event["type"], payload=event))
    save_score_records(db, interview_id, records, commit=False)
    interview = db.get(Interview, interview_id)
    if interview.started_at is None:
        interview.started_at = datetime.now()
    interview.status = "finished" if snapshot["finished"] else "running"
    if snapshot["finished"] and interview.ended_at is None:
        interview.ended_at = datetime.now()
    if message_id:
        db.add(InterviewSubmission(interview_id=interview_id, message_id=message_id,
                                    request_hash=request_hash, events=numbered))
    db.commit()
    return numbered


def load_scores(db: Session, interview_id: str) -> list[QuestionScore]:
    stmt = (
        select(QuestionScore)
        .where(QuestionScore.interview_id == interview_id)
        .order_by(QuestionScore.id)
    )
    return list(db.scalars(stmt))


def load_events(db: Session, interview_id: str) -> list[InterviewEvent]:
    stmt = (
        select(InterviewEvent)
        .where(InterviewEvent.interview_id == interview_id)
        .order_by(InterviewEvent.seq)
    )
    return list(db.scalars(stmt))


def append_system_event(db: Session, interview_id: str, event: dict) -> int | None:
    """追加一条**不推进轮次版本**的审计事件（语音取消/丢弃/合成失败等）。

    与 ``commit_turn`` 的区别：这类事件不改变面试业务状态，因此不动 version
    ——否则会把正在进行的一轮变成 stale_turn，把打断这种正常操作变成客户端重连。

    seq 取现有最大值 +1；同时把 runtime.next_seq 单调抬高，避免后续
    ``commit_turn`` 复用同一个 seq 造成事件流乱序。
    """
    runtime = db.get(InterviewRuntime, interview_id)
    interview = db.get(Interview, interview_id)
    if runtime is None or interview is None or interview.status == "cancelled":
        return None
    current = db.scalar(
        select(func.max(InterviewEvent.seq)).where(InterviewEvent.interview_id == interview_id)
    )
    seq = (current if current is not None else -1) + 1
    db.add(
        InterviewEvent(
            interview_id=interview_id, seq=seq, type=str(event.get("type", "unknown")), payload=event
        )
    )
    runtime.next_seq = max(runtime.next_seq, seq + 1)
    db.commit()
    return seq
