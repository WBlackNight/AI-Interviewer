"""Password recovery via a registered email and a single-use graphical challenge."""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from app.api.dependencies import auth_work
from app.api.account_inputs import EmailCodeInput
from app.config import get_settings
from app.db import get_db
from app.models.entities import Account, AccountProfile, AccountSession, AuthChallenge
from app.services import account_security as security
from app.services.accounts import now_utc, lock_account, hash_password

router=APIRouter(prefix='/api/auth/recovery',tags=['accounts'])

class Identity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(min_length=3,max_length=32,pattern=r'^[a-z0-9_]+$')
    email:str=Field(max_length=254)
    @field_validator('username',mode='before')
    @classmethod
    def clean_username(cls,value):return value.strip().lower() if isinstance(value,str) else value
    @field_validator('email')
    @classmethod
    def clean_email(cls,value):return EmailCodeInput.email_format(value)

class SendCode(Identity):
    captcha_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    captcha_code:str=Field(min_length=1,max_length=10)

class ResetPassword(Identity):
    challenge_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    code:str=Field(pattern=r'^\d{6}$')
    new_password:SecretStr=Field(min_length=8,max_length=128)
    password_confirm:SecretStr=Field(min_length=8,max_length=128)
    @model_validator(mode='after')
    def matching(self):
        if self.new_password.get_secret_value()!=self.password_confirm.get_secret_value():
            raise HTTPException(422,'两次新密码不一致')
        return self

def matching_account(db,payload):
    return db.scalar(select(Account).join(AccountProfile,AccountProfile.account_id==Account.id)
        .where(Account.username==payload.username,AccountProfile.email==payload.email))

@router.post('/code',dependencies=[Depends(auth_work)])
def send_recovery_code(payload:SendCode,db:Session=Depends(get_db)):
    if not security.mail_available(get_settings()):
        raise HTTPException(503,'邮件服务尚未配置，暂时无法通过邮箱找回密码')
    security.consume(db,payload.captcha_id,payload.captcha_code,'register')
    result={'challenge_id':secrets.token_hex(16),'expires_in':600,'retry_after':60}
    account=matching_account(db,payload)
    if not account:return result
    lock_account(db,account.id)
    rows=list(db.scalars(select(AuthChallenge).where(AuthChallenge.account_id==account.id,
        AuthChallenge.created_at>now_utc()-timedelta(hours=1))))
    if len(rows)>=5 or any(r.created_at>now_utc()-timedelta(seconds=60) for r in rows):return result
    code=f'{secrets.randbelow(1000000):06}'
    db.execute(update(AuthChallenge).where(AuthChallenge.account_id==account.id,
        AuthChallenge.purpose=='password_recovery').values(consumed=1))
    item=security.challenge(db,'password_recovery',code,account.id,payload.email)
    identifier=item.id;db.commit()
    try:security.send_code(get_settings(),payload.email,code,'password_recovery')
    except HTTPException:
        db.execute(delete(AuthChallenge).where(AuthChallenge.id==identifier));db.commit();return result
    return {**result,'challenge_id':identifier}

@router.post('/reset',dependencies=[Depends(auth_work)])
def reset_password(payload:ResetPassword,db:Session=Depends(get_db)):
    account=matching_account(db,payload)
    if not account:raise HTTPException(400,'验证失败，请检查信息或重新获取验证码')
    security.consume(db,payload.challenge_id,payload.code,'password_recovery',account.id,payload.email)
    lock_account(db,account.id)
    db.refresh(account)
    if matching_account(db,payload) is None:raise HTTPException(400,'邮箱信息已更改，请重新验证')
    account.password_hash=hash_password(payload.new_password.get_secret_value())
    db.execute(delete(AccountSession).where(AccountSession.account_id==account.id))
    db.execute(delete(AuthChallenge).where(AuthChallenge.account_id==account.id))
    db.commit()
    return {'reset':True}
