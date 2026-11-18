"""Authenticated profile and reauthenticated account security operations."""
import asyncio
import secrets
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException,Request,Header,Query
from fastapi.responses import Response
from sqlalchemy import select,delete,update,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.config import get_settings
from app.db import get_db
from app.models.entities import Account,AccountProfile,AccountSession,AuthChallenge
from app.services.accounts import require_account,verify_password,hash_password,lock_account,now_utc,issue_session,bearer_token,token_hash
from app.services import account_security as security, revision_export
from app.api.dependencies import auth_work

router=APIRouter(prefix='/api',tags=['profile'])

@router.get('/account/revision-export')
def export_revision_data(db:Session=Depends(get_db),account:Account=Depends(require_account)):
    return revision_export.export_revision_data(db, account.id)

from app.api.account_inputs import ProfileInput, EmailCodeInput, EmailConfirm, PasswordInput, ReauthenticateInput

def reauthenticate(db,account,password):
    lock_account(db,account.id);db.refresh(account)
    if not verify_password(password.get_secret_value(),account.password_hash):raise HTTPException(403,'当前密码不正确，请重新输入')

@router.get('/account/security')
def capabilities(db:Session=Depends(get_db),account:Account=Depends(require_account)):
    settings=get_settings()
    return {'email_available':security.mail_available(settings),'email_mode':settings.mail_mode,
        'test_mail_url':'http://localhost:8025/' if settings.mail_mode=='local_test' else None,
        'avatar_max_bytes':security.AVATAR_LIMIT,
        'active_sessions':db.scalar(select(func.count()).select_from(AccountSession).where(
            AccountSession.account_id==account.id,AccountSession.expires_at>now_utc()))}

@router.post('/account/sessions/revoke-others',dependencies=[Depends(auth_work)])
def revoke_other_sessions(payload:ReauthenticateInput,db:Session=Depends(get_db),
        account:Account=Depends(require_account),authorization:str|None=Header(default=None)):
    reauthenticate(db,account,payload.current_password)
    current=token_hash(bearer_token(authorization))
    count=db.execute(delete(AccountSession).where(AccountSession.account_id==account.id,
        AccountSession.token_hash!=current)).rowcount
    db.commit()
    return {'revoked':count}

@router.patch('/account/profile')
def update_profile(payload:ProfileInput,db:Session=Depends(get_db),account:Account=Depends(require_account)):
    from app.models.entities import AccountDetails
    lock_account(db, account.id)
    details = db.get(AccountDetails, account.id)
    version = details.version if details else 0
    if payload.expected_version is not None and payload.expected_version != version:
        raise HTTPException(409, '资料已在其他页面修改，请重新读取后再保存')
    if details is None:
        details = AccountDetails(account_id=account.id, gender=None, age=None, bio='', version=0)
        db.add(details)
    changes = payload.model_dump(exclude_unset=True, exclude={'expected_version'})
    changed = False
    if 'nickname' in changes:
        profile = security.profile_row(db, account)
        changed = profile.nickname != changes.pop('nickname')
        profile.nickname = payload.nickname
    for field, value in changes.items():
        if getattr(details, field) != value:
            setattr(details, field, value)
            changed = True
    if changed:
        details.version += 1
    db.commit()
    return security.profile_data(db,account)

@router.post('/account/avatar')
async def upload_avatar(request:Request,db:Session=Depends(get_db),account:Account=Depends(require_account),size:int=Query(256,ge=128,le=512)):
    raw=bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>security.AVATAR_LIMIT:raise HTTPException(413,'头像不能超过2MB')
                raw.extend(chunk)
    except TimeoutError:raise HTTPException(408,'头像上传超时，请重试') from None
    media=request.headers.get('content-type','').split(';')[0].lower()
    avatar=await run_in_threadpool(security.normalize_avatar,bytes(raw),media,size)
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
    if payload.purpose in ('email_bind','email_change'):
        if row.email and payload.purpose=='email_bind':raise HTTPException(409,'账户已绑定邮箱，无需重复绑定')
        if not row.email and payload.purpose=='email_change':raise HTTPException(409,'请先绑定邮箱')
        if not payload.email:raise HTTPException(422,'请输入要绑定的邮箱')
        if payload.email==row.email:raise HTTPException(422,'新邮箱不能与当前邮箱相同')
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
    if payload.purpose not in ('email_bind','email_change') or not payload.email:raise HTTPException(422,'邮箱验证请求不完整')
    reauthenticate(db,account,payload.current_password);db.commit()
    security.consume(db,payload.challenge_id,payload.code,payload.purpose,account.id,payload.email)
    reauthenticate(db,account,payload.current_password);row=security.profile_row(db,account)
    if row.email and payload.purpose=='email_bind':raise HTTPException(409,'账户已绑定邮箱')
    if not row.email and payload.purpose=='email_change':raise HTTPException(409,'请先绑定邮箱')
    db.execute(delete(AuthChallenge).where(AuthChallenge.account_id==account.id,
        AuthChallenge.purpose.in_(('password_recovery','password_change'))))
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
