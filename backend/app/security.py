"""资源访问凭据与有限的文本 PII 脱敏。"""
import hashlib
import re
import secrets

from sqlalchemy.orm import Session
from app.models.entities import AccessGrant, ResourceOwner


def issue_access(db: Session, kind: str, resource_id: str) -> str:
    token = secrets.token_hex(32)
    db.add(AccessGrant(resource_kind=kind, resource_id=resource_id,
                       token_hash=hashlib.sha256(token.encode()).hexdigest()))
    return token


def has_access(db: Session, kind: str, resource_id: str, token: str | None) -> bool:
    if not token or len(token) != 64:
        return False
    owner = db.get(ResourceOwner, (kind, resource_id))
    if owner:
        from app.services.accounts import account_for_token
        account = account_for_token(db, token)
        return bool(account and account.id == owner.account_id)
    grant = db.get(AccessGrant, (kind, resource_id))
    return bool(grant and secrets.compare_digest(grant.token_hash,
                hashlib.sha256(token.encode()).hexdigest()))


def sanitize_pii(text: str) -> str:
    text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[ID]", text)
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[PHONE]", text)
    return re.sub(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
