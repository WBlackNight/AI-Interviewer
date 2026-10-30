"""Single-use challenges, normalized profile data and bounded raster processing."""
import base64
import hashlib
import hmac
import io
import secrets
import smtplib
import ssl
import threading
import unicodedata
from datetime import timedelta
from email.message import EmailMessage
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from app.models.entities import AccountProfile, AuthChallenge
from app.services.accounts import now_utc
from app.config import get_settings

_KEY = secrets.token_bytes(32)
AVATAR_LIMIT = 2 * 1024 * 1024
_AVATAR_WORK=threading.BoundedSemaphore(2)

def generate_code():
    return ''.join(secrets.choice('23456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(5))

def digest(identifier, code):
    key=get_settings().auth_challenge_secret
    return hmac.new(key.encode() if key else _KEY,(identifier+':'+code.strip().upper()).encode(),hashlib.sha256).hexdigest()

def challenge(db,purpose,code,account_id=None,context='',seconds=600):
    now=now_utc()
    db.execute(delete(AuthChallenge).where(AuthChallenge.created_at < now-timedelta(days=1)))
    identifier=secrets.token_hex(16)
    item=AuthChallenge(id=identifier,purpose=purpose,account_id=account_id,context=context,
        secret_hash=digest(identifier,code),created_at=now,expires_at=now+timedelta(seconds=seconds))
    db.add(item);db.flush()
    return item

def consume(db,identifier,code,purpose,account_id=None,context=None):
    filters=[AuthChallenge.id==identifier,AuthChallenge.purpose==purpose,
        AuthChallenge.account_id==account_id,AuthChallenge.consumed==0,
        AuthChallenge.expires_at>now_utc(),AuthChallenge.attempts<5]
    if context is not None:filters.append(AuthChallenge.context==context)
    row=db.execute(update(AuthChallenge).where(*filters).values(attempts=AuthChallenge.attempts+1)
        .returning(AuthChallenge.secret_hash,AuthChallenge.context)).first()
    # Failed attempts persist independently of later form errors.
    db.commit()
    if not row or not hmac.compare_digest(row[0],digest(identifier,code)):
        raise HTTPException(400,'验证码错误、已过期或已使用，请重新获取')
    used=db.execute(update(AuthChallenge).where(AuthChallenge.id==identifier,AuthChallenge.consumed==0)
        .values(consumed=1)).rowcount
    db.commit()
    if not used:raise HTTPException(400,'验证码已使用，请重新获取')
    return row[1]

def captcha(db):
    code=generate_code();row=challenge(db,'register',code,seconds=120)
    image=Image.new('RGB',(190,64),'#edf5ef');draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=34)
    for _ in range(8):
        draw.line([(secrets.randbelow(190),secrets.randbelow(64)),(secrets.randbelow(190),secrets.randbelow(64))],fill='#b3ccbc',width=1)
    for i,char in enumerate(code):draw.text((13+i*33,9+secrets.randbelow(10)),char,font=font,fill='#254e3a')
    output=io.BytesIO();image.save(output,format='PNG');db.commit()
    return {'captcha_id':row.id,'image':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),'expires_in':120}

def profile_data(db,account):
    row=db.get(AccountProfile,account.id)
    return {'id':account.id,'username':account.username,'nickname':row.nickname if row else '',
        'email':row.email if row else None,'email_verified':bool(row and row.email),
        'avatar_version':row.avatar_version if row else None}

def profile_row(db,account):
    row=db.get(AccountProfile,account.id)
    if row is None:row=AccountProfile(account_id=account.id,nickname='');db.add(row);db.flush()
    return row

def nickname(value):
    value=unicodedata.normalize('NFC',value.strip())
    if not 1<=len(value)<=32 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('昵称应为1–32个可见字符')
    return value

def normalize_avatar(raw,media):
    allowed={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}
    if media not in allowed:raise HTTPException(415,'头像仅支持 JPG、PNG、WebP 静态图片')
    if not raw or len(raw)>AVATAR_LIMIT:raise HTTPException(413,'头像不能为空且不能超过2MB')
    if not _AVATAR_WORK.acquire(blocking=False):raise HTTPException(429,'图片处理繁忙，请稍后重试')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format!=allowed[media] or getattr(source,'n_frames',1)!=1:
                raise ValueError('format')
            if not (32<=source.width<=4096 and 32<=source.height<=4096):raise ValueError('dimensions')
            source.load()
            image=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(256,256))
            image.info.clear()
            out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
    except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError):
        raise HTTPException(422,'图片无法读取，请使用32–4096像素的有效静态图片') from None
    finally:_AVATAR_WORK.release()

def mail_available(settings):
    return settings.mail_mode in ('local_test','smtp')

def send_code(settings,address,code,purpose):
    if not mail_available(settings):raise HTTPException(503,'邮件发送尚未配置，请稍后再试')
    local=settings.mail_mode=='local_test'
    if local and settings.smtp_host not in ('127.0.0.1','localhost','::1'):
        raise HTTPException(503,'本机测试邮件配置无效')
    if not local and settings.smtp_security=='none':raise HTTPException(503,'SMTP需要启用TLS')
    message=EmailMessage();message['Subject']='青栈 · '+('绑定邮箱' if purpose=='email_bind' else '修改密码')+'验证码'
    message['From']=settings.mail_from;message['To']=address
    message.set_content(('本机测试邮件，不发送至外部。\n' if local else '')+f'你的验证码是：{code}\n10分钟内有效，仅限本次操作。请勿向他人透露。')
    try:
        cls=smtplib.SMTP_SSL if settings.smtp_security=='ssl' and not local else smtplib.SMTP
        with cls(settings.smtp_host,settings.smtp_port,timeout=8) as smtp:
            if not local and settings.smtp_security=='starttls':smtp.starttls(context=ssl.create_default_context())
            if not local and settings.smtp_username:smtp.login(settings.smtp_username,settings.smtp_password or '')
            smtp.send_message(message)
    except (OSError,smtplib.SMTPException):
        raise HTTPException(503,'邮件未能发送，请稍后重试；未完成邮箱验证') from None
