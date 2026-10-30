"""账户准备计划：范围固定、版本保护、活动练习复用，关联与面试原子保存。"""
from collections import Counter
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.factories import load_assets
from app.models.entities import PreparationPlan, PreparationPractice, Interview, ResourceOwner
from app.services.accounts import lock_account, now_utc
from app.services.interviews import save_interview
from app.services.history import summaries
from app.services.review import account_review
from app.services.practice import available_themes, practice_plan
from app.services.revision import revision_today

MAX_PLANS = 50


def owned_plan(db, account_id, plan_id, expected_version):
    lock_account(db, account_id)
    row = db.scalar(select(PreparationPlan).where(PreparationPlan.account_id == account_id, PreparationPlan.id == plan_id))
    if row is None: raise HTTPException(404, '准备计划不存在')
    if row.version != expected_version: raise HTTPException(409, '计划已在其他页面更新，请刷新后再操作')
    return row


def create_plan(db, account_id, payload, settings):
    lock_account(db, account_id)
    if db.scalar(select(func.count()).select_from(PreparationPlan).where(PreparationPlan.account_id == account_id)) >= MAX_PLANS:
        raise HTTPException(409, '最多保存50个计划，请先移除不需要的已归档计划')
    trees, bank = load_assets(settings)
    tree = trees.get(payload.position)
    try:
        if tree is None: raise ValueError('position')
        practice_plan(tree, bank, payload.position, payload.difficulty, payload.themes, settings.max_plan_themes)
    except ValueError:
        raise HTTPException(422, '岗位或主题当前不可练，请刷新可用范围') from None
    moment = now_utc()
    row = PreparationPlan(account_id=account_id, name=payload.name, position=payload.position, themes=payload.themes,
        difficulty=payload.difficulty, target_date=payload.target_date, status='active', version=0,
        created_at=moment, updated_at=moment)
    db.add(row); db.flush()
    return {'id': row.id, 'version': row.version}


def update_plan(db, account_id, plan_id, payload):
    row = owned_plan(db, account_id, plan_id, payload.expected_version)
    changes = payload.model_dump(exclude_unset=True, exclude={'expected_version'})
    if any(getattr(row, key) != value for key, value in changes.items()):
        for key, value in changes.items(): setattr(row, key, value)
        row.version += 1; row.updated_at = now_utc()
    return {'id': row.id, 'version': row.version}


def remove_plan(db, account_id, plan_id, expected_version):
    row = owned_plan(db, account_id, plan_id, expected_version)
    if row.status != 'archived': raise HTTPException(409, '请先归档计划，再移除')
    db.execute(delete(PreparationPractice).where(PreparationPractice.plan_id == row.id))
    db.delete(row)
    return {'deleted': True}


def list_plans(db, account_id, settings, *, position=None, status=None, plan_id=None, offset=0, limit=8):
    rows = list(db.scalars(select(PreparationPlan).where(PreparationPlan.account_id == account_id)
        .order_by(PreparationPlan.created_at.desc(), PreparationPlan.id.desc())))
    trees, bank = load_assets(settings)
    positions = [{'id': key, 'display_name': trees[key].display_name if key in trees else key}
                 for key in sorted({row.position for row in rows})]
    if position is not None: rows = [row for row in rows if row.position == position]
    today = revision_today()
    counts = Counter(row.status for row in rows)
    past_target = sum(row.status == 'active' and row.target_date is not None and row.target_date < today for row in rows)
    if status is not None: rows = [row for row in rows if row.status == status]
    if plan_id is not None: rows = [row for row in rows if row.id == plan_id]
    total = len(rows); rows = rows[offset:offset + limit]; ids = [row.id for row in rows]
    summaries = select(PreparationPractice.plan_id.label('plan_id'), func.max(PreparationPractice.id).label('latest_id'),
        func.count().filter(Interview.status == 'finished').label('finished_count')).join(Interview,
        Interview.id == PreparationPractice.interview_id).join(ResourceOwner,
        (ResourceOwner.resource_kind == 'interview') & (ResourceOwner.resource_id == Interview.id))
    summaries = summaries.where(PreparationPractice.plan_id.in_(ids), ResourceOwner.account_id == account_id).group_by(PreparationPractice.plan_id).subquery()
    linked = db.execute(select(summaries.c.plan_id, summaries.c.finished_count, Interview.id, Interview.status)
        .select_from(summaries).join(PreparationPractice, PreparationPractice.id == summaries.c.latest_id)
        .join(Interview, Interview.id == PreparationPractice.interview_id)).all() if ids else []
    latest, finished = {}, Counter()
    for plan_id, count, interview_id, interview_status in linked:
        latest[plan_id] = {'interview_id': interview_id, 'status': interview_status}
        finished[plan_id] = count
    allowed = {key: set(available_themes(tree, bank, key)) for key, tree in trees.items()}
    items = [{'id': row.id, 'name': row.name, 'position': row.position, 'themes': row.themes, 'difficulty': row.difficulty,
              'target_date': row.target_date.isoformat() if row.target_date else None, 'status': row.status,
              'version': row.version, 'created_at': row.created_at.isoformat() + 'Z', 'updated_at': row.updated_at.isoformat() + 'Z',
              'available': bool(row.themes) and len(row.themes) <= settings.max_plan_themes and all(theme in allowed.get(row.position, set()) for theme in row.themes),
              'latest_practice': latest.get(row.id), 'finished_count': finished[row.id]} for row in rows]
    return {'items': items, 'total': total, 'offset': offset, 'limit': limit, 'has_more': offset + len(rows) < total,
            'positions': positions, 'counts': {'active': counts['active'], 'archived': counts['archived'], 'past_target': past_target},
            'today': today.isoformat(), 'timezone': 'Asia/Shanghai', 'max_plans': MAX_PLANS}


# 计划记录先核对共同归属，按关联顺序分页；计数不受状态和分页影响。
def list_plan_practices(db, account_id, plan_id, skill_tree_dir, *, status=None, offset=0, limit=8):
    plan = db.scalar(select(PreparationPlan).where(PreparationPlan.id == plan_id, PreparationPlan.account_id == account_id))
    if plan is None:
        raise HTTPException(404, '准备计划不存在')
    owned = select(Interview, ResourceOwner.created_at).join(PreparationPractice,
        PreparationPractice.interview_id == Interview.id).join(ResourceOwner,
        (ResourceOwner.resource_kind == 'interview') & (ResourceOwner.resource_id == Interview.id)).where(
        PreparationPractice.plan_id == plan.id, ResourceOwner.account_id == account_id)
    counts = dict(db.execute(owned.with_only_columns(Interview.status, func.count()).group_by(Interview.status)).all())
    if status is not None:
        owned = owned.where(Interview.status == status)
    total = db.scalar(select(func.count()).select_from(owned.subquery()))
    rows = db.execute(owned.order_by(PreparationPractice.id.desc()).offset(offset).limit(limit)).all()
    items = summaries(db, [row[0] for row in rows], skill_tree_dir)
    for item, (_, saved_at) in zip(items, rows):
        item['saved_at'] = saved_at.replace(tzinfo=timezone.utc).isoformat()
    return {'plan': {'id': plan.id, 'name': plan.name, 'position': plan.position, 'themes': plan.themes,
                     'difficulty': plan.difficulty, 'status': plan.status,
                     'target_date': plan.target_date.isoformat() if plan.target_date else None},
            'items': items, 'total': total, 'offset': offset, 'limit': limit, 'has_more': offset + len(items) < total,
            'status': status, 'status_counts': {key: counts.get(key, 0) for key in ('created', 'running', 'finished', 'cancelled')},
            'timezone': 'Asia/Shanghai'}


# 来源单独读取：校验面试与计划的共同归属，名称和日期不进入报告或导出。
def practice_source(db, account_id, interview_id):
    owner = db.get(ResourceOwner, ('interview', interview_id))
    if owner is None or owner.account_id != account_id or db.get(Interview, interview_id) is None:
        raise HTTPException(404, '练习不存在')
    row = db.scalar(select(PreparationPlan).join(PreparationPractice,
        PreparationPractice.plan_id == PreparationPlan.id).where(
        PreparationPractice.interview_id == interview_id, PreparationPlan.account_id == account_id))
    return {'source': {'id': row.id, 'name': row.name, 'status': row.status,
                       'target_date': row.target_date.isoformat() if row.target_date else None} if row else None}


# 概览只取三个活动计划，优先有目标日期的最近目标；不加载题库或创建练习。
def plan_dashboard(db, account_id, today):
    owned = select(PreparationPlan).where(PreparationPlan.account_id == account_id)
    counts = dict(db.execute(owned.with_only_columns(PreparationPlan.status, func.count())
        .group_by(PreparationPlan.status)).all())
    active = owned.where(PreparationPlan.status == 'active')
    past_target = db.scalar(select(func.count()).select_from(active.where(PreparationPlan.target_date < today).subquery()))
    rows = db.scalars(active.order_by(PreparationPlan.target_date.asc().nullslast(),
        PreparationPlan.created_at.desc(), PreparationPlan.id.desc()).limit(3))
    return {'counts': {'active': counts.get('active', 0), 'archived': counts.get('archived', 0), 'past_target': past_target},
            'items': [{'id': row.id, 'name': row.name, 'position': row.position,
                       'target_date': row.target_date.isoformat() if row.target_date else None} for row in rows], 'limit': 3}


def start_plan_practice(db, account_id, plan_id, expected_version, settings):
    row = owned_plan(db, account_id, plan_id, expected_version)
    if row.status != 'active': raise HTTPException(409, '计划已归档，请先恢复计划或到记录页继续已有练习')
    active = db.scalar(select(Interview).join(PreparationPractice, PreparationPractice.interview_id == Interview.id)
        .join(ResourceOwner, (ResourceOwner.resource_kind == 'interview') & (ResourceOwner.resource_id == Interview.id))
        .where(PreparationPractice.plan_id == row.id, ResourceOwner.account_id == account_id,
               Interview.status.in_(['created', 'running'])).order_by(PreparationPractice.id.desc()).limit(1))
    if active:
        return {'interview_id': active.id, 'account_owned': True, 'access_token': None, 'preparation_plan_id': row.id, 'reused': True}
    trees, bank = load_assets(settings)
    try:
        tree = trees.get(row.position)
        if tree is None: raise ValueError('position')
        plan = practice_plan(tree, bank, row.position, row.difficulty, row.themes, settings.max_plan_themes)
    except ValueError:
        raise HTTPException(422, '计划范围当前不可练，请保留旧记录并新建有效范围的计划') from None
    created = save_interview(db, row.position, row.difficulty, plan, account_id=account_id, commit=False)
    db.add(PreparationPractice(plan_id=row.id, interview_id=created.interview_id))
    db.flush()
    return {**created.model_dump(), 'preparation_plan_id': row.id, 'reused': False}


# 复盘复用原主问题等权、版本与重复题口径，每次只读一个主题的有界完成场次。
def plan_review(db, account_id, plan_id, settings, *, theme=None, offset=0, limit=4):
    plan = db.scalar(select(PreparationPlan).where(PreparationPlan.id == plan_id, PreparationPlan.account_id == account_id))
    if plan is None:
        raise HTTPException(404, '准备计划不存在')
    result = account_review(db, account_id, settings.skill_tree_dir, position=plan.position,
        theme=theme, offset=offset, limit=limit, plan_id=plan.id)
    return {**result, 'preparation_plan_id': plan.id, 'weak_score': settings.weak_score}
