"""Validated account profile, email and password request bodies."""
import re
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.services import account_security as security

EMAIL_PATTERN = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    gender: Literal['male', 'female', 'other'] | None = None
    age: int | None = Field(default=None, strict=True, ge=1, le=120)
    bio: str = Field(default='', strict=True, max_length=160)
    expected_version: int | None = Field(default=None, strict=True, ge=0)

    @field_validator('nickname')
    @classmethod
    def clean_name(cls, value):
        return security.nickname(value) if value is not None else None

    @field_validator('bio')
    @classmethod
    def clean_bio(cls, value):
        value = value.strip()
        if any(ord(char) < 32 and char not in '\n\t' for char in value):
            raise ValueError('简介包含不可见字符')
        return value

    @model_validator(mode='after')
    def valid_changes(self):
        if not self.model_fields_set - {'expected_version'}:
            raise ValueError('请填写需要修改的资料')
        if 'nickname' in self.model_fields_set and self.nickname is None:
            raise ValueError('昵称不能为空')
        return self


class EmailCodeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    current_password: SecretStr = Field(min_length=8, max_length=128)
    purpose: str = Field(pattern=r'^(email_bind|email_change|password_change)$')
    email: str | None = Field(default=None, max_length=254)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        if value is None:
            return value
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value) or '..' in value or value.startswith('.') or '.@' in value:
            raise ValueError('邮箱格式不正确')
        local, domain = value.rsplit('@', 1)
        if len(local) > 64 or any(len(label) > 63 for label in domain.split('.')):
            raise ValueError('邮箱格式不正确')
        return value


class EmailConfirm(EmailCodeInput):
    challenge_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    code: str = Field(pattern=r'^\d{6}$')


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    current_password: SecretStr = Field(min_length=8, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    password_confirm: SecretStr = Field(min_length=8, max_length=128)
    challenge_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    code: str | None = Field(default=None, pattern=r'^\d{6}$')

    @model_validator(mode='after')
    def matching(self):
        new = self.new_password.get_secret_value()
        if new != self.password_confirm.get_secret_value():
            raise HTTPException(422, '两次新密码不一致')
        if new == self.current_password.get_secret_value():
            raise HTTPException(422, '新密码不能与当前密码相同')
        return self


class ReauthenticateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    current_password: SecretStr = Field(min_length=8, max_length=128)
