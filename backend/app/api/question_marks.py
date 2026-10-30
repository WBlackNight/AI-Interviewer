"""个人题单接口；所有操作只作用于当前账户，读写均不调用模型。"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.factories import load_assets
from app.models.entities import Account
from app.services.accounts import require_account
from app.services.question_marks import add_mark, list_marks, owned_mark, update_mark

router = APIRouter(prefix='/api/account/question-marks', tags=['question-marks'])


class MarkCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    position: str = Field(strict=True, min_length=1, max_length=64)
    question_id: str = Field(strict=True, min_length=1, max_length=64)


class MarkUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['todo', 'done']
    expected_version: int = Field(strict=True, ge=0)


@router.get('')
def read_marks(db: Session = Depends(get_db), account: Account = Depends(require_account),
               position: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
               status: Literal['todo', 'done'] | None = None,
               q: Annotated[str | None, Query(max_length=100)] = None,
               offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
               limit: Annotated[int, Query(ge=1, le=24)] = 8):
    trees, bank = load_assets(get_settings())
    return list_marks(db, account.id, trees, bank, position=position, status=status, query=q, offset=offset, limit=limit)


@router.post('')
def create_mark(payload: MarkCreate, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    trees, bank = load_assets(get_settings())
    result = add_mark(db, account.id, payload.position, payload.question_id, trees, bank)
    db.commit()
    return result


@router.patch('/{mark_id}')
def patch_mark(mark_id: str, payload: MarkUpdate, db: Session = Depends(get_db), account: Account = Depends(require_account)):
    result = update_mark(db, account.id, mark_id, payload.status, payload.expected_version)
    db.commit()
    return result


@router.delete('/{mark_id}')
def remove_mark(mark_id: str, expected_version: Annotated[int, Query(ge=0)],
                db: Session = Depends(get_db), account: Account = Depends(require_account)):
    row = owned_mark(db, account.id, mark_id, expected_version)
    db.delete(row)
    db.commit()
    return {'deleted': True}
