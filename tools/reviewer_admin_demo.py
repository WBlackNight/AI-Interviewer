"""Run the reviewer administrator demo on localhost with its own database."""
import argparse
from getpass import getpass
import json
import os
import sys

from run_server import BACKEND, server_environment


def prepare_demo(password, port):
    demo_dir = BACKEND / '.reviewer-admin'
    demo_dir.mkdir(exist_ok=True)
    os.environ.update(server_environment(demo_dir / 'demo.sqlite3', offline=True))
    os.environ.update({
        'ADMIN_ACCOUNT_IDS': '',
        'ADMIN_VIEWER_ACCOUNT_IDS': '',
        'CORS_ORIGINS': json.dumps([f'http://localhost:{port}', f'http://127.0.0.1:{port}']),
    })
    # An independent working directory keeps the regular backend .env out of the demo.
    os.chdir(demo_dir)
    sys.path.insert(0, str(BACKEND))

    from sqlalchemy import select
    from app.config import get_settings
    from app.db import SessionLocal, engine
    from app.manage_database import REVIEWER_USERNAME, create_reviewer_account
    from app.models.entities import Account
    from app.schema_versions import upgrade_schema
    from app.services.accounts import verify_password

    upgrade_schema(engine)
    with SessionLocal.begin() as db:
        lookup = select(Account).where(Account.username == REVIEWER_USERNAME)
        account = db.scalar(lookup)
        if account is None:
            create_reviewer_account(db, password)
            account = db.scalar(lookup)
        elif not verify_password(password, account.password_hash):
            raise ValueError('密码与已有演示账号不匹配。')
        os.environ['ADMIN_ACCOUNT_IDS'] = account.id
    get_settings.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=3222)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口须为 1 至 65535。')
    password = os.environ.pop('QINGZHAN_REVIEWER_PASSWORD', None)
    if password is None:
        if not sys.stdin.isatty():
            parser.exit(1, '请在交互终端输入演示账号密码。\n')
        password = getpass('评委后台演示密码：')
    if not 8 <= len(password) <= 128:
        parser.exit(1, '密码长度须为 8 至 128 个字符。\n')
    try:
        prepare_demo(password, args.port)
    except ValueError as error:
        parser.exit(1, f'{error}\n')

    import uvicorn

    print(f'评委后台演示  http://localhost:{args.port}/admin')
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
