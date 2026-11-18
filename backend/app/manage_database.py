"""Database maintenance and explicit reviewer account provisioning."""
import argparse
from getpass import getpass
import json
import sys
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, engine
from app.models.entities import Account
from app.schema_versions import schema_status, upgrade_schema
from app.services.accounts import hash_password


REVIEWER_USERNAME = 'admin'


def create_reviewer_account(db, password):
    if not 8 <= len(password) <= 128:
        raise ValueError('密码长度须为 8 至 128 个字符。')
    db.add(Account(username=REVIEWER_USERNAME, password_hash=hash_password(password)))
    db.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'upgrade', 'create-reviewer'))
    args = parser.parse_args()
    if args.command == 'create-reviewer':
        if not sys.stdin.isatty():
            parser.exit(1, '请在支持隐藏输入的交互终端中运行。\n')
        password = getpass('评委体验账号密码：')
        if password != getpass('再次输入密码：'):
            parser.exit(1, '两次输入的密码不一致。\n')
        try:
            upgrade_schema(engine)
            with SessionLocal.begin() as db:
                create_reviewer_account(db, password)
        except ValueError as error:
            parser.exit(1, f'{error}\n')
        except IntegrityError:
            parser.exit(1, '用户名 admin 已存在，现有账户保持原样。\n')
        print('已创建评委体验账号 admin，权限为普通用户。')
        return
    if args.command == 'upgrade':
        upgrade_schema(engine)
    print(json.dumps(schema_status(engine)))


if __name__ == '__main__':
    main()
