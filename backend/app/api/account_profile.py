"""Authenticated profile and reauthenticated account security operations."""
import asyncio
import re
import secrets
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException,Request,Header
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field,SecretStr,field_validator,model_validator
from sqlalchemy import select,delete,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.config import get_settings
from app.db import get_db
from app.models.entities import Account,AccountProfile,AccountSession,AuthChallenge
from app.services.accounts import require_account,verify_password,hash_password,lock_account,now_utc,issue_session
from app.services import account_security as security
from app.api.accounts import auth_work

router=APIRouter(prefix='/api',tags=['profile'])

class ProfileInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    nickname:str=Field(min_length=1,max_length=32)
    @field_validator('nickname')
    @classmethod
    def clean_name(cls,value):return security.nickname(value)

class EmailCodeInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    current_password:SecretStr=Field(min_length=12,max_length=128)
    purpose:str=Field(pattern=r'^(email_bind|password_change)$')
    email:str|None=Field(default=None,max_length=254)
    @field_validator('email')
    @classmethod
    def email_format(cls,value):
        if value is None:return value
        value=value.strip().lower()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",value) or '..' in value or len(value.split('@')[0])>64 or value.startswith('.') or '.@' in value or any(len(label)>63 for label in value.rsplit('@',1)[-1].split('.')):
            raise ValueError('邮箱格式不正确')
        return value

class EmailConfirm(EmailCodeInput):
    challenge_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    code:str=Field(pattern=r'^\d{6}$')

class PasswordInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    current_password:SecretStr=Field(min_length=12,max_length=128)
    new_password:SecretStr=Field(min_length=12,max_length=128)
    password_confirm:SecretStr=Field(min_length=12,max_length=128)
    challenge_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    code:str|None=Field(default=None,pattern=r'^\d{6}$')
    @model_validator(mode='after')
    def matching(self):
        if self.new_password.get_secret_value()!=self.password_confirm.get_secret_value():raise HTTPException(422,'两次新密码不一致')
        if self.new_password.get_secret_value()==self.current_password.get_secret_value():raise HTTPException(422,'新密码不能与当前密码相同')
        return self

def reauthenticate(db,account,password):
    lock_account(db,account.id);db.refresh(account)
    if not verify_password(password.get_secret_value(),account.password_hash):raise HTTPException(403,'当前密码不正确，请重新输入')

@router.get('/account/security')
def capabilities(account:Account=Depends(require_account)):
    settings=get_settings()
    return {'email_available':security.mail_available(settings),'email_mode':settings.mail_mode,
        'test_mail_url':'http://localhost:8025/' if settings.mail_mode=='local_test' else None,
        'avatar_max_bytes':security.AVATAR_LIMIT}

@router.patch('/account/profile')
def update_profile(payload:ProfileInput,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    lock_account(db,account.id);security.profile_row(db,account).nickname=payload.nickname;db.commit()
    return security.profile_data(db,account)

@router.post('/account/avatar')
async def upload_avatar(request:Request,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    raw=bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>security.AVATAR_LIMIT:raise HTTPException(413,'头像不能超过2MB')
                raw.extend(chunk)
    except TimeoutError:raise HTTPException(408,'头像上传超时，请重试') from None
    media=request.headers.get('content-type','').split(';')[0].lower()
    avatar=await run_in_threadpool(security.normalize_avatar,bytes(raw),media)
    lock_account(db,account.id);row=security.profile_row(db,account)
    row.avatar=avatar;row.avatar_version=secrets.token_hex(16);db.commit()
    return security.profile_data(db,account)

@router.get('/account/avatar')
def read_avatar(db:Session=Depends(get_db),account:Account=Depends(require_account)):
    row=db.get(AccountProfile,account.id)
    if not row or not row.avatar:raise HTTPException(404,'尚未设置头像')
    return Response(row.avatar,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.delete('/account/avatar')
def remove_avatar(db:Session=Depends(get_db),account:Account=Depends(require_account)):
    lock_account(db,account.id);row=security.profile_row(db,account);row.avatar=row.avatar_version=None;db.commit()
    return security.profile_data(db,account)

@router.post('/account/email/code',dependencies=[Depends(auth_work)])
def email_code(payload:EmailCodeInput,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    reauthenticate(db,account,payload.current_password)
    row=security.profile_row(db,account)
    if payload.purpose=='email_bind':
        if row.email:raise HTTPException(409,'账户已绑定邮箱，无需重复绑定')
        if not payload.email:raise HTTPException(422,'请输入要绑定的邮箱')
        address=payload.email
        if db.scalar(select(AccountProfile.account_id).where(AccountProfile.email==address)):raise HTTPException(409,'该邮箱不可用于绑定')
    else:
        if not row.email:raise HTTPException(409,'请先绑定邮箱')
        address=row.email
    since=now_utc()-timedelta(hours=1)
    rows=list(db.scalars(select(AuthChallenge).where(AuthChallenge.account_id==account.id,AuthChallenge.created_at>since)))
    if any(r.created_at>now_utc()-timedelta(seconds=60) for r in rows):raise HTTPException(429,'请60秒后再获取验证码',headers={'Retry-After':'60'})
    if len(rows)>=5:raise HTTPException(429,'本小时验证码次数已用完，请稍后再试')
    code=f'{secrets.randbelow(1000000):06}'
    # First commit a reservation: concurrent sends cannot bypass cooldown.
    db.execute(update(AuthChallenge).where(AuthChallenge.account_id==account.id,AuthChallenge.purpose==payload.purpose).values(consumed=1))
    item=security.challenge(db,payload.purpose,code,account.id,address);identifier=item.id;db.commit()
    try:security.send_code(get_settings(),address,code,payload.purpose)
    except HTTPException:
        db.execute(delete(AuthChallenge).where(AuthChallenge.id==identifier));db.commit();raise
    return {'challenge_id':identifier,'expires_in':600,'retry_after':60,'delivery':get_settings().mail_mode}

@router.post('/account/email/confirm',dependencies=[Depends(auth_work)])
def confirm_email(payload:EmailConfirm,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    if payload.purpose!='email_bind' or not payload.email:raise HTTPException(422,'邮箱验证请求不完整')
    reauthenticate(db,account,payload.current_password);db.commit()
    security.consume(db,payload.challenge_id,payload.code,'email_bind',account.id,payload.email)
    reauthenticate(db,account,payload.current_password);row=security.profile_row(db,account)
    if row.email:raise HTTPException(409,'账户已绑定邮箱')
    row.email=payload.email
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'该邮箱不可用于绑定') from None
    return security.profile_data(db,account)

@router.post('/account/password',dependencies=[Depends(auth_work)])
def change_password(payload:PasswordInput,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    reauthenticate(db,account,payload.current_password);profile=db.get(AccountProfile,account.id)
    email=profile.email if profile else None
    if email:
        db.commit()
        if not payload.challenge_id or not payload.code:raise HTTPException(422,'请输入已绑定邮箱收到的验证码')
        security.consume(db,payload.challenge_id,payload.code,'password_change',account.id,email)
        reauthenticate(db,account,payload.current_password)
    account.password_hash=hash_password(payload.new_password.get_secret_value())
    db.execute(delete(AccountSession).where(AccountSession.account_id==account.id))
    db.execute(delete(AuthChallenge).where(AuthChallenge.account_id==account.id))
    token,expires=issue_session(db,account.id);db.commit()
    return {'account':security.profile_data(db,account),'access_token':token,'expires_at':expires.isoformat()+'Z','other_sessions_revoked':True}
