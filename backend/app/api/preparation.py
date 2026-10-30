"""主动准备计划API：账户范围、明确写入、版本保护与原练习流程接入。"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.entities import Account
from app.services.accounts import require_account
from app.services.preparation import create_plan, list_plans, list_plan_practices, plan_review, practice_source, remove_plan, start_plan_practice, update_plan

router = APIRouter(prefix='/api/account/preparation-plans', tags=['preparation-plans'])


class PlanFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, strict=True, min_length=1, max_length=80)
    target_date: date | None = None

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value): return value.strip() if isinstance(value, str) else value

    @field_validator('target_date', mode='before')
    @classmethod
    def calendar(cls, value):
        if value is None: return None
        if not isinstance(value, str): raise ValueError('使用日历日期')
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not 2000 <= parsed.year <= 2100: raise ValueError('日期超出范围')
        return parsed


class PlanCreate(PlanFields):
    name: str = Field(strict=True, min_length=1, max_length=80)
    position: str = Field(strict=True, min_length=1, max_length=64)
    themes: list[Annotated[str, Field(strict=True, min_length=1, max_length=64)]] = Field(min_length=1, max_length=12)
    difficulty: Literal['easy', 'mid', 'hard'] = 'mid'


class PlanVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(strict=True, ge=0)


class PlanUpdate(PlanFields):
    expected_version: int = Field(strict=True, ge=0)
    status: Literal['active', 'archived'] | None = None

    @model_validator(mode='after')
    def valid_update(self):
        fields = self.model_fields_set - {'expected_version'}
        if not fields or any(getattr(self, key) is None for key in fields - {'target_date'}): raise ValueError('空修改无效')
        return self


@router.get('')
def read(db: Session = Depends(get_db), account: Account = Depends(require_account),
         position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
         status: Literal['active', 'archived'] | None = None,
         plan_id: Annotated[str | None, Query(pattern='^[a-f0-9]{32}$')] = None,
         offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0, limit: Annotated[int, Query(ge=1, le=20)] = 8):
    return list_plans(db, account.id, get_settings(), position=position, status=status, plan_id=plan_id, offset=offset, limit=limit)


@router.get('/source/{interview_id}')
def source(interview_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    return practice_source(db, account.id, interview_id)


@router.post('')
def create(payload: PlanCreate, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    result = create_plan(db, account.id, payload, get_settings()); db.commit(); return result


@router.patch('/{plan_id}')
def update(plan_id: str, payload: PlanUpdate, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    result = update_plan(db, account.id, plan_id, payload); db.commit(); return result


@router.delete('/{plan_id}')
def remove(plan_id: str, expected_version: Annotated[int, Query(ge=0)], db: Session = Depends(get_db), account: Account = Depends(require_account)):
    result = remove_plan(db, account.id, plan_id, expected_version); db.commit(); return result


@router.post('/{plan_id}/practice')
def practice(plan_id: str, payload: PlanVersion, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    result = start_plan_practice(db, account.id, plan_id, payload.expected_version, get_settings()); db.commit(); return result


@router.get('/{plan_id}/practices')
def practices(plan_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account),
              status: Literal['created', 'running', 'finished', 'cancelled'] | None = None,
              offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
              limit: Annotated[int, Query(ge=1, le=20)] = 8):
    return list_plan_practices(db, account.id, plan_id, get_settings().skill_tree_dir, status=status, offset=offset, limit=limit)


@router.get('/{plan_id}/review')
def review(plan_id: str, db: Session = Depends(get_db), account: Account = Depends(require_account),
           theme: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
           offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
           limit: Annotated[int, Query(ge=1, le=10)] = 4):
    return plan_review(db, account.id, plan_id, get_settings(), theme=theme, offset=offset, limit=limit)
