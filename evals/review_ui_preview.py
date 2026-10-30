"""浏览器手工验收用隔离预览：空闲的localhost:8000/3000，默认存活30分钟。

先完成frontend生产构建，再运行本脚本。只使用合成账户和规则评分。
本地演示登录 ui_review_demo / local-demo-password-2026；不要用于任何部署。
创建输出目录中的stop文件即可结束，清理本次临时数据库及自有进程。
可用--preview-minutes设置1–1440分钟；--seed-tasks为三场报告加入复习任务。
--seed-dates同时加入任务，并预置今日、逾期和未安排日期。
"""
import asyncio
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone

from smoke_e2e import BACKEND, ROOT, Server, request
from practice_smoke import complete
from revision_smoke import update


def assert_port_free(port):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


async def seed(server, extended=False, seed_tasks=False, seed_dates=False):
    if not server.test_captcha:
        import sys
        sys.path.insert(0,str(server.db_path.parents[1]))
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.models.entities import Account
        from app.services.accounts import hash_password
        engine=create_engine('sqlite:///'+server.db_path.as_posix())
        with Session(engine) as db:
            db.add(Account(username='ui_review_demo',password_hash=hash_password('local-demo-password-2026')));db.commit()
        engine.dispose()
        account=request(server.base,'/api/auth/login',{'username':'ui_review_demo','password':'local-demo-password-2026'})
    else:
        account = request(server.base, "/api/auth/register", {"username": "ui_review_demo", "password": "local-demo-password-2026"})
    headers = {"Authorization": "Bearer " + account["access_token"]}
    for position, theme in [("java_backend", "MySQL"), ("java_backend", "MySQL"), ("python_backend", "Python基础")]:
        created = request(server.base, "/api/interview", {"position": position, "themes": [theme]}, headers)
        await complete(server, {**created, "access_token": account["access_token"]}, [theme])
        if seed_tasks:
            request(server.base, f'/api/account/interviews/{created["interview_id"]}/revision-tasks', {}, headers)
    if seed_dates:
        from datetime import date
        board = request(server.base, "/api/account/revision-tasks", headers=headers)
        today = date.fromisoformat(board["today"])
        for task, day in zip(board["items"], [None, today.isoformat(), (today - timedelta(days=1)).isoformat()]):
            update(server.base, "/api/account/revision-tasks/" + task["id"], headers, {"due_date": day})
    if extended:
        # 额外20场真实离线完成记录，让历史/任务两页按钮可实际验收。
        for _ in range(20):
            created = request(server.base, "/api/interview", {"position": "java_backend", "themes": ["MySQL"]}, headers)
            await complete(server, {**created, "access_token": account["access_token"]}, ["MySQL"])
            request(server.base, f'/api/account/interviews/{created["interview_id"]}/revision-tasks', {}, headers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extended-history", action="store_true", help="合成23场已完成记录和20个任务，验收分页")
    parser.add_argument("--seed-tasks", action="store_true", help="为三场预览报告加入真实离线复习任务")
    parser.add_argument("--seed-dates", action="store_true", help="预置今日、逾期和未安排任务，同时启用--seed-tasks")
    parser.add_argument("--preview-minutes", type=int, default=30, choices=range(1, 1441), metavar="1..1440", help="预览服务存活分钟数，默认30")
    args = parser.parse_args()
    assert_port_free(8000); assert_port_free(3000)
    os.environ["CORS_ORIGINS"] = '["http://localhost:3000"]'
    with tempfile.TemporaryDirectory(prefix=".ui-review-", dir=BACKEND) as directory:
        task_dir = Path(directory).resolve()
        server = Server(task_dir / "preview.sqlite3")
        server.port, server.base = 8000, "http://127.0.0.1:8000"
        frontend = None
        try:
            server.start()
            asyncio.run(seed(server, args.extended_history, args.seed_tasks or args.seed_dates, args.seed_dates))
            frontend = subprocess.Popen([shutil.which("node"), str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "start", "-H", "127.0.0.1", "-p", "3000"], cwd=ROOT / "frontend",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            print(json.dumps({"url": "http://localhost:3000/account", "stop_file": str(task_dir / "stop"),
                              "synthetic_only": True, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=args.preview_minutes)).isoformat()}), flush=True)
            deadline = time.monotonic() + args.preview_minutes * 60
            while time.monotonic() < deadline and not (task_dir / "stop").exists():
                if frontend.poll() is not None:
                    raise RuntimeError("预览前端未能启动，请核对生产构建")
                time.sleep(.2)
        finally:
            if frontend is not None and frontend.poll() is None:
                frontend.terminate()
                try:
                    frontend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    frontend.kill(); frontend.wait(timeout=5)
            server.stop()


if __name__ == "__main__":
    main()
