"""Exact-question practice and comparison, shared by the REST report entry point."""
from fastapi import HTTPException
from sqlalchemy import select

from app.domain import PlanItem
from app.models.entities import Interview, ResourceOwner
from app.repositories import get_interview
from app.schemas import InterviewCreateResponse
from app.score_origin import question_version
from app.security import has_access
from app.services.accounts import lock_account
from app.services.interviews import save_interview
from app.services.report import build_report


def enrich_retry_report(db, interview, report, tree, bank, token):
    interview_id = interview.id
    owner = db.get(ResourceOwner, ("interview", interview_id))
    for row in report["per_question"]:
        question = bank.get(row["question_id"])
        row["can_retry"] = bool(owner and report["is_complete"] and row["probe_depth"] == 0
            and question and not question.is_coding and question.position == interview.position
            and question.content == row["content"]
            and row["scoring_origin"].get("question_version") in (None, question_version(question)))
    report["retry_comparison"] = None
    if interview.plan:
        source_id = interview.plan[0].get("source_interview_id")
        question_id = interview.plan[0].get("question_id")
        if source_id and question_id and has_access(db, "interview", source_id, token):
            source = get_interview(db, source_id)
            if source:
                original_report = build_report(db, source, tree)
                original = next((row for row in original_report["per_question"]
                                 if row["question_id"] == question_id and row["probe_depth"] == 0), None)
                current = next((row for row in report["per_question"]
                                if row["question_id"] == question_id and row["probe_depth"] == 0), None)
                if original and (not current or original["content"] == current["content"]):
                    report["retry_comparison"] = {"source_interview_id": source_id,
                        "original": original, "current": current}
    return report


def start_question_retry(db, account_id, interview_id, question_id, trees, bank):
    lock_account(db, account_id)
    owner = db.get(ResourceOwner, ("interview", interview_id))
    if owner is None or owner.account_id != account_id:
        raise HTTPException(404, "练习记录不存在")
    source = get_interview(db, interview_id)
    if source is None or source.status != "finished":
        raise HTTPException(409, "请完成本场面试后再逐题复练")
    original = next((row for row in build_report(db, source, trees.get(source.position))["per_question"]
                     if row["question_id"] == question_id and row["probe_depth"] == 0), None)
    question = bank.get(question_id)
    if not original or not question or question.is_coding or question.position != source.position:
        raise HTTPException(422, "这道题暂不支持逐题复练")
    if original["content"] != question.content:
        raise HTTPException(409, "题目内容已更新，请从题库开始新的主题练习")
    if original["scoring_origin"].get("question_version") not in (None, question_version(question)):
        raise HTTPException(409, "题目要求已更新，请从题库开始新的主题练习")
    existing = db.scalar(select(Interview).join(ResourceOwner,
        (ResourceOwner.resource_kind == "interview") & (ResourceOwner.resource_id == Interview.id))
        .where(ResourceOwner.account_id == account_id, Interview.status.in_(["created", "running"]),
               Interview.plan[0]["source_interview_id"].as_string() == interview_id,
               Interview.plan[0]["question_id"].as_string() == question_id)
        .order_by(Interview.started_at.desc(), Interview.id.desc()).limit(1))
    if existing:
        return InterviewCreateResponse(access_token=None, account_owned=True, interview_id=existing.id,
            position=existing.position, plan=existing.plan, ws_url="/ws/interview/" + existing.id)
    plan = [PlanItem(theme=question.theme, weight=1.0, difficulty=question.difficulty,
                     question_count=1, question_id=question.id, source_interview_id=source.id)]
    return save_interview(db, source.position, question.difficulty, plan, account_id=account_id)
