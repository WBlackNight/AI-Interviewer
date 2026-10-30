"""从已完成报告显式加入复习任务；同源主题去重，不重置用户进度。"""
from collections import Counter
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, func, case, or_

from app.agent.skill_tree import load_skill_tree
from app.models.entities import Interview, ResourceOwner, RevisionTask, RevisionPractice, RevisionSchedule, RevisionNote
from app.factories import load_assets
from app.schemas import PlanItemOut, RevisionPracticeResponse
from app.services.accounts import lock_account, now_utc
from app.services.report import build_report
from app.services.interviews import save_interview
from app.services.practice import practice_plan
from app.services.revision_links import latest_practices


def revision_today():
    """当前复习日历固定北京时间 UTC+08:00，不依赖宿主或浏览器时区。"""
    return (now_utc() + timedelta(hours=8)).date()


def schedules(db, task_ids):
    if not task_ids:
        return {}
    return dict(db.execute(select(RevisionSchedule.task_id, RevisionSchedule.due_date)
                           .where(RevisionSchedule.task_id.in_(task_ids))).all())


def note_data(row=None):
    return {"content": row.content if row else "", "version": row.version if row else 0,
            "updated_at": row.updated_at.isoformat() + "Z" if row and row.updated_at else None}


def notes(db, task_ids):
    if not task_ids:
        return {}
    return {row.task_id: note_data(row) for row in db.scalars(select(RevisionNote).where(RevisionNote.task_id.in_(task_ids)))}


def task_data(row, practice=None, due_date=None, note=None):
    return {"id": row.id, "interview_id": row.interview_id, "position": row.position,
            "theme": row.theme, "source_score": row.source_score, "weak_score": row.weak_score,
            "focus_points": row.focus_points, "status": row.status,
            "created_at": row.created_at.isoformat() + "Z",
            "completed_at": row.completed_at.isoformat() + "Z" if row.completed_at else None,
            "latest_practice": practice, "due_date": due_date.isoformat() if due_date else None,
            "note": note if note is not None else note_data()}


def add_revision_tasks(db, account_id, interview_id):
    lock_account(db, account_id)
    owner = db.get(ResourceOwner, ("interview", interview_id))
    if not owner or owner.account_id != account_id:
        raise HTTPException(403, "请先在练习记录中认领该面试，或选择所属面试")
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise HTTPException(404, "面试不存在")
    if interview.status != "finished":
        raise HTTPException(409, "仅已完成面试可加入复习任务")
    report = build_report(db, interview, None)
    if not report["weak_points"]:
        raise HTTPException(422, "本场没有达到待补强条件的主题")
    existing = {r.theme: r for r in db.scalars(select(RevisionTask).where(
        RevisionTask.account_id == account_id, RevisionTask.interview_id == interview_id))}
    rows, added = [], 0
    for theme in report["weak_points"]:
        row = existing.get(theme)
        if row is None:
            points = []
            for turn in report["per_question"]:
                if turn["theme"] == theme:
                    for point in turn["key_points_missed"] or []:
                        if isinstance(point, str) and point.strip():
                            point = point.strip()[:300]
                            if point not in points and len(points) < 8:
                                points.append(point)
            row = RevisionTask(account_id=account_id, interview_id=interview_id,
                position=interview.position, theme=theme, source_score=report["theme_avg"][theme],
                weak_score=report["weak_score"], focus_points=points)
            db.add(row)
            added += 1
        rows.append(row)
    db.commit()
    practices = latest_practices(db, [r.id for r in rows])
    dates = schedules(db, [r.id for r in rows])
    saved_notes = notes(db, [r.id for r in rows])
    return {"items": [task_data(r, practices.get(r.id), dates.get(r.id), saved_notes.get(r.id)) for r in rows], "added": added, "existing": len(rows) - added}


def list_revision_tasks(db, account_id, skill_tree_dir, *, status=None, position=None, due="all", offset=0, limit=20,
                        query=None, note_filter="all"):
    today = revision_today()
    owned = select(RevisionTask, RevisionSchedule.due_date).outerjoin(
        RevisionSchedule, RevisionSchedule.task_id == RevisionTask.id).where(RevisionTask.account_id == account_id)
    positions = list(db.scalars(select(RevisionTask.position).where(
        RevisionTask.account_id == account_id).distinct().order_by(RevisionTask.position)))
    if position is not None:
        owned = owned.where(RevisionTask.position == position)
    # 在所属任务内匹配主题或笔记；转义LIKE通配符，不让搜索扩大为全量匹配。
    query = (query.strip() or None) if query is not None else None
    note_scope = select(RevisionNote.task_id).where(RevisionNote.task_id == RevisionTask.id)
    if query:
        owned = owned.where(or_(RevisionTask.theme.icontains(query, autoescape=True),
            note_scope.where(RevisionNote.content.icontains(query, autoescape=True)).exists()))
    if note_filter != "all":
        has_note = note_scope.where(RevisionNote.content != "").exists()
        owned = owned.where(has_note if note_filter == "with" else ~has_note)
    counts = Counter(dict(db.execute(select(RevisionTask.status, func.count()).where(
        RevisionTask.id.in_(owned.with_only_columns(RevisionTask.id))).group_by(RevisionTask.status)).all()))
    if status is not None:
        owned = owned.where(RevisionTask.status == status)
    date_scope = owned.subquery()
    predicates = {"today": date_scope.c.due_date == today, "overdue": date_scope.c.due_date < today,
                  "upcoming": date_scope.c.due_date > today, "unscheduled": date_scope.c.due_date.is_(None)}
    date_counts = dict(zip(predicates, db.execute(select(*[
        func.coalesce(func.sum(case((condition, 1), else_=0)), 0) for condition in predicates.values()
    ])).one()))
    filters = {"today": RevisionSchedule.due_date == today, "overdue": RevisionSchedule.due_date < today,
               "upcoming": RevisionSchedule.due_date > today, "unscheduled": RevisionSchedule.due_date.is_(None)}
    if due != "all":
        owned = owned.where(filters[due])
    total = db.scalar(select(func.count()).select_from(owned.subquery()))
    order = [RevisionTask.created_at.desc(), RevisionTask.id.desc()]
    if due in ("today", "overdue", "upcoming"):
        order.insert(0, RevisionSchedule.due_date.asc())
    rows = db.execute(owned.order_by(*order).offset(offset).limit(limit)).all()
    trees = load_skill_tree(skill_tree_dir)
    practices = latest_practices(db, [r.id for r, _ in rows])
    saved_notes = notes(db, [r.id for r, _ in rows])
    return {"items": [task_data(r, practices.get(r.id), day, saved_notes.get(r.id)) for r, day in rows], "total": total, "offset": offset, "limit": limit,
            "has_more": offset + len(rows) < total, "status": status, "position": position,
            "due": due, "date_counts": date_counts, "today": today.isoformat(), "timezone": "Asia/Shanghai",
            "query": query, "note_filter": note_filter,
            "counts": {"todo": counts["todo"], "done": counts["done"]},
            "positions": [{"id": p, "display_name": trees[p].display_name if p in trees else p} for p in positions]}


def update_revision_task(db, account_id, task_id, **changes):
    lock_account(db, account_id)
    row = db.scalar(select(RevisionTask).where(RevisionTask.id == task_id, RevisionTask.account_id == account_id))
    if row is None:
        raise HTTPException(404, "复习任务不存在")
    if "status" in changes and row.status != changes["status"]:
        row.status = changes["status"]
        row.completed_at = now_utc() if row.status == "done" else None
    schedule = db.get(RevisionSchedule, task_id)
    if "due_date" in changes:
        if changes["due_date"] is None:
            if schedule is not None:
                db.delete(schedule)
            schedule = None
        elif schedule is None:
            schedule = RevisionSchedule(task_id=task_id, due_date=changes["due_date"])
            db.add(schedule)
        else:
            schedule.due_date = changes["due_date"]
    db.commit()
    return task_data(row, latest_practices(db, [row.id]).get(row.id), schedule.due_date if schedule else None,
                     note_data(db.get(RevisionNote, row.id)))


def get_revision_note(db, account_id, task_id):
    task = db.scalar(select(RevisionTask).where(RevisionTask.id == task_id, RevisionTask.account_id == account_id))
    if task is None:
        raise HTTPException(404, "复习任务不存在")
    return note_data(db.get(RevisionNote, task_id))


def update_revision_note(db, account_id, task_id, content, expected_version):
    lock_account(db, account_id)
    task = db.scalar(select(RevisionTask).where(RevisionTask.id == task_id, RevisionTask.account_id == account_id))
    if task is None:
        raise HTTPException(404, "复习任务不存在")
    row = db.get(RevisionNote, task_id)
    version = row.version if row else 0
    if version != expected_version:
        raise HTTPException(409, "笔记已在其他页面更新，请读取最新版本后合并；当前草稿未保存")
    if content == (row.content if row else ""):
        return note_data(row)
    if row is None:
        row = RevisionNote(task_id=task_id, content=content, version=1, updated_at=now_utc())
        db.add(row)
    else:
        row.content = content
        row.version += 1
        row.updated_at = now_utc()
    db.commit()
    return note_data(row)


def start_revision_practice(db, account_id, task_id, settings):
    lock_account(db, account_id)
    task = db.scalar(select(RevisionTask).where(RevisionTask.id == task_id, RevisionTask.account_id == account_id))
    if task is None:
        raise HTTPException(404, "复习任务不存在")
    source = db.get(Interview, task.interview_id)
    owner = db.get(ResourceOwner, ("interview", task.interview_id))
    if source is None or not owner or owner.account_id != account_id or source.status != "finished":
        raise HTTPException(409, "任务来源已不可用，请刷新任务列表")
    active = db.scalar(select(Interview).join(RevisionPractice, RevisionPractice.interview_id == Interview.id)
        .join(ResourceOwner, (ResourceOwner.resource_kind == "interview") & (ResourceOwner.resource_id == Interview.id))
        .where(RevisionPractice.task_id == task.id, ResourceOwner.account_id == account_id,
               Interview.status.in_(["created", "running"]))
        .order_by(RevisionPractice.id.desc()).limit(1))
    if active:
        return RevisionPracticeResponse(interview_id=active.id, position=active.position,
            plan=[PlanItemOut(**p) for p in active.plan], ws_url=f"/ws/interview/{active.id}",
            account_owned=True, access_token=None, revision_task_id=task.id, reused=True)
    trees, bank = load_assets(settings)
    tree = trees.get(task.position)
    if tree is None or task.position != source.position:
        raise HTTPException(422, "任务岗位当前不可练，请从首页选择可用岗位")
    try:
        plan = practice_plan(tree, bank, task.position, source.difficulty, [task.theme], settings.max_plan_themes)
    except ValueError:
        raise HTTPException(422, "任务主题当前没有可用知识题，请从首页选择其他专项") from None
    created = save_interview(db, task.position, source.difficulty, plan, account_id=account_id, commit=False)
    db.add(RevisionPractice(task_id=task.id, interview_id=created.interview_id))
    db.commit()
    return RevisionPracticeResponse(**created.model_dump(), revision_task_id=task.id, reused=False)
