"""Bounded administrative reads, exports and versioned review metadata."""
from typing import Annotated, Literal
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, HTTPException, Path
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.factories import load_assets
from app.models.entities import Account
from app.services import admin
from app.services import admin_operations as operations

router = APIRouter(prefix='/api/admin', tags=['admin'], dependencies=[Depends(admin.require_admin)])
Search = Annotated[str, Query(max_length=80)]
Position = Annotated[str, Query(max_length=64, pattern=r'^[a-z0-9_]*$')]
Offset = Annotated[int, Query(ge=0, le=100000)]
Limit = Annotated[int, Query(ge=1, le=50)]
Sort = Literal['default', 'newest', 'oldest', 'name', 'difficulty']
ReviewStatus = Literal['pending', 'approved', 'needs_revision']


def permission(name):
    def check(request: Request, account: Account = Depends(admin.require_admin), db: Session = Depends(get_db)):
        if not admin.capabilities(account.id)['permissions'].get(name):
            operations.audit(db, account.id, 'permission_denied', name, request.state.admin_request_id, outcome='denied')
            db.commit()
            raise HTTPException(403, '当前角色没有此操作权限，请联系管理员。')
        return account
    return check


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: ReviewStatus
    note: str = Field(default='', max_length=500)
    expected_version: int = Field(strict=True, ge=0)
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def explain_revision(self):
        if self.status == 'needs_revision' and len(self.note.strip()) < 5:
            raise ValueError('请说明需要修改的问题')
        return self


@router.get('/overview')
def overview(days: Annotated[int, Query(ge=7, le=90)] = 14, db: Session = Depends(get_db),
             account: Account = Depends(admin.require_admin)):
    _, bank = load_assets(get_settings())
    return {**admin.overview(db, bank, days), **admin.capabilities(account.id)}


@router.get('/interviews')
def interviews(q: Search = '', position: Position = '', status: Literal['', 'created', 'running', 'finished', 'cancelled'] = '',
               offset: Offset = 0, limit: Limit = 10, start: date | None = None, end: date | None = None,
               sort: Literal['default', 'newest', 'oldest'] = 'default', db: Session = Depends(get_db)):
    return admin.interviews(db, query=q.strip(), position=position, status=status, offset=offset, limit=limit,
                            start=start, end=end, sort=sort)


@router.get('/accounts')
def accounts(q: Search = '', bound: Literal['', 'bound', 'unbound'] = '', offset: Offset = 0,
             limit: Limit = 10, start: date | None = None, end: date | None = None,
             sort: Literal['default', 'newest', 'oldest', 'name'] = 'default', db: Session = Depends(get_db)):
    return admin.accounts(db, query=q.strip(), bound=bound, offset=offset, limit=limit, start=start, end=end, sort=sort)


@router.get('/questions')
def questions(q: Search = '', position: Position = '', difficulty: Literal['', 'easy', 'mid', 'hard'] = '',
              kind: Literal['', 'knowledge', 'coding'] = '', offset: Offset = 0, limit: Limit = 10,
              review: Literal['', 'pending', 'approved', 'needs_revision'] = '',
              sort: Literal['default', 'name', 'difficulty'] = 'default', db: Session = Depends(get_db)):
    _, bank = load_assets(get_settings())
    return operations.questions(db, bank, query=q.strip(), position=position, difficulty=difficulty,
                                kind=kind, review=review, sort=sort, offset=offset, limit=limit)


@router.patch('/questions/{question_id}/review')
def save_review(question_id: Annotated[str, Path(pattern=r'^[A-Za-z0-9_.-]{1,64}$')], payload: ReviewInput,
                request: Request, db: Session = Depends(get_db), account: Account = Depends(permission('review'))):
    _, bank = load_assets(get_settings())
    return operations.save_review(db, bank, account.id, question_id, payload, request.state.admin_request_id)


@router.get('/audit')
def audit_entries(q: Search = '', action: Literal['', 'data_export', 'question_review', 'permission_denied'] = '',
                  outcome: Literal['', 'succeeded', 'denied'] = '', start: date | None = None, end: date | None = None,
                  offset: Offset = 0, limit: Limit = 10, db: Session = Depends(get_db),
                  account: Account = Depends(permission('audit'))):
    return operations.audit_list(db, query=q.strip(), action=action, outcome=outcome,
                                 start=start, end=end, offset=offset, limit=limit)


@router.get('/export')
def export_data(request: Request, resource: Literal['interviews', 'questions', 'accounts'], q: Search = '',
                position: Position = '', status: Literal['', 'created', 'running', 'finished', 'cancelled'] = '',
                difficulty: Literal['', 'easy', 'mid', 'hard'] = '', kind: Literal['', 'knowledge', 'coding'] = '',
                bound: Literal['', 'bound', 'unbound'] = '', review: Literal['', 'pending', 'approved', 'needs_revision'] = '',
                start: date | None = None, end: date | None = None, sort: Sort = 'default',
                db: Session = Depends(get_db), account: Account = Depends(permission('export'))):
    allowed = {'interviews': {'default', 'newest', 'oldest'}, 'questions': {'default', 'name', 'difficulty'},
               'accounts': {'default', 'newest', 'oldest', 'name'}}
    if sort not in allowed[resource]:
        raise HTTPException(422, '当前列表不支持此排序方式。')
    _, bank = load_assets(get_settings())
    content, count = operations.export_csv(db, bank, resource,
        dict(query=q.strip(), position=position, status=status, difficulty=difficulty, kind=kind, bound=bound,
             review=review, start=start, end=end, sort=sort), account.id, request.state.admin_request_id)
    return Response(content, media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="qingzhan-{resource}.csv"', 'X-Export-Rows': str(count)})
