"""本地账户、数据库会话与匿名资源归属；不依赖外部身份服务。"""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import threading
import time
from collections import OrderedDict

from fastapi import Depends, Header, HTTPException
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import Account, AccountSession, ResourceOwner

ITERATIONS = 600_000
SESSION_DAYS = 7


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# 不存在的用户名也执行相同密码派生；常量是校验器而非可用账户密码。
DUMMY_HASH = f'pbkdf2_sha256${ITERATIONS}${"00" * 16}${"00" * 32}'


def issue_session(db: Session, account_id: str):
    db.execute(delete(AccountSession).where(AccountSession.expires_at <= now_utc()))
    token = secrets.token_hex(32)
    expires = now_utc() + timedelta(days=SESSION_DAYS)
    db.add(AccountSession(token_hash=token_hash(token), account_id=account_id, expires_at=expires))
    return token, expires


def account_for_token(db: Session, token: str | None) -> Account | None:
    if not token or len(token) != 64:
        return None
    session = db.get(AccountSession, token_hash(token))
    if not session or session.expires_at <= now_utc():
        return None
    return db.get(Account, session.account_id)


def bearer_token(authorization: str | None):
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) != 64:
        raise HTTPException(401, "登录凭据无效或已过期")
    return token


def optional_account(db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    token = bearer_token(authorization)
    if token is None:
        return None
    account = account_for_token(db, token)
    if account is None:
        raise HTTPException(401, "登录凭据无效或已过期，请重新登录")
    return account


def require_account(account: Account | None = Depends(optional_account)):
    if account is None:
        raise HTTPException(401, "请先登录")
    return account


def attach_owner(db: Session, kind: str, resource_id: str, account_id: str):
    db.add(ResourceOwner(resource_kind=kind, resource_id=resource_id, account_id=account_id))


def lock_account(db: Session, account_id: str):
    found = db.execute(update(Account).where(Account.id == account_id).values(username=Account.username)).rowcount
    if not found:
        raise HTTPException(401, "账户已失效，请重新登录")


class AuthThrottle:
    """单进程、按来源地址限制散列工作；固定窗口，最多保留1024个地址。"""
    def __init__(self):
        self.rows = OrderedDict()
        self.lock = threading.Lock()
        self.work = threading.BoundedSemaphore(2)

    def check(self, key: str):
        with self.lock:
            now = time.monotonic()
            start, count = self.rows.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= 20:
                raise HTTPException(429, "登录尝试过于频繁，请稍后再试", headers={"Retry-After": "60"})
            self.rows[key] = (start, count + 1)
            self.rows.move_to_end(key)
            while len(self.rows) > 1024:
                self.rows.popitem(last=False)
