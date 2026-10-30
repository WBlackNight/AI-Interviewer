"""无需构建的完整首页联调：3000原生入口、3100已有Next构建、8000隔离离线后端。

python evals/native_home_preview.py --preview-minutes 240
端口必须空闲；只停止本脚本自己的进程，不修改.env或开发数据库。
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from native_home_gateway import create_gateway
from review_ui_preview import assert_port_free, seed
from smoke_e2e import BACKEND, ROOT, Server, OPENER, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-minutes", type=int, choices=range(1, 1441), default=240, metavar="1..1440")
    parser.add_argument("--extended-history", action="store_true", help="预置23场合成报告与复习任务以验收分页")
    parser.add_argument("--seed-notes", action="store_true", help="为Java/Python各一项预置合成笔记以验收搜索")
    parser.add_argument("--seed-history-states", action="store_true", help="补充尚未开始、进行中和已取消记录")
    parser.add_argument("--seed-plan-history", action="store_true", help="补充一份含10场合成练习的计划以验收分页")
    parser.add_argument("--voice-provider", choices=('disabled', 'dummy', 'doubao'), default='disabled', help='显式选择语音替身或真实豆包；默认关闭')
    parser.add_argument('--local-mail',action='store_true',help='启动127.0.0.1测试SMTP和8025收件箱，不向外发送邮件')
    parser.add_argument('--restore-db',type=Path,help='从backend内的隔离预览数据库副本恢复，跳过基础种子创建')
    args = parser.parse_args()
    if not (ROOT / "frontend/.next/BUILD_ID").is_file():
        raise RuntimeError("未找到现有生产构建；此脚本不会自动构建")
    for port in (3000, 3100, 8000):
        assert_port_free(port)
    with tempfile.TemporaryDirectory(prefix=".native-preview-", dir=BACKEND) as directory:
        task_dir = Path(directory).resolve()
        backend = Server(task_dir / "preview.sqlite3", voice_provider=args.voice_provider,test_captcha=False)
        if args.restore_db:
            source=args.restore_db.resolve()
            if not source.is_relative_to(BACKEND.resolve()) or not source.is_file():
                raise ValueError('restore database must be an existing file under backend')
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(source)) as old,closing(sqlite3.connect(backend.db_path)) as restored:old.backup(restored)
        backend.port, backend.base = 8000, "http://127.0.0.1:8000"
        frontend, gateway = None, None
        mail_servers=[]
        try:
            if args.local_mail:
                from local_test_mail import start_test_mail
                mail_servers=start_test_mail()
                os.environ.update(MAIL_MODE='local_test',SMTP_HOST='127.0.0.1',SMTP_PORT='1025',SMTP_SECURITY='none')
            os.environ["CORS_ORIGINS"] = '["http://localhost:3000"]'
            backend.start()
            if not args.restore_db:
                asyncio.run(seed(backend, extended=args.extended_history, seed_tasks=True, seed_dates=True))
            if args.seed_notes:
                account = request(backend.base, '/api/auth/login', {'username': 'ui_review_demo', 'password': 'local-demo-password-2026'})
                headers = {'Authorization': 'Bearer ' + account['access_token']}
                tasks = request(backend.base, '/api/account/revision-tasks?limit=50', headers=headers)['items']
                from revision_notes_smoke import put
                for position, content in [('java_backend', '解释B+树的范围查询与磁盘IO。\n100%只是用于验证字面搜索的合成内容。'),
                                          ('python_backend', '区分引用与对象，解释浅拷贝和深拷贝。\n下次用嵌套列表举例。')]:
                    task = next(item for item in tasks if item['position'] == position)
                    put(backend.base, '/api/account/revision-tasks/' + task['id'] + '/note', headers, content, 0)
            if args.seed_history_states:
                from history_filters_smoke import seed_states
                account = request(backend.base, '/api/auth/login', {'username': 'ui_review_demo', 'password': 'local-demo-password-2026'})
                asyncio.run(seed_states(backend, account['access_token']))
            plan_history_url = None
            if args.seed_plan_history:
                from preparation_preview import seed_plan_history
                plan_history_url = asyncio.run(seed_plan_history(backend))
            frontend = subprocess.Popen([shutil.which("node"), str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "start", "-H", "127.0.0.1", "-p", "3100"], cwd=ROOT / "frontend",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            deadline = time.monotonic() + 20
            while True:
                if frontend.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("已有Next构建启动失败")
                try:
                    with OPENER.open("http://127.0.0.1:3100/account", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            gateway = create_gateway(3000)
            threading.Thread(target=gateway.serve_forever, daemon=True).start()
            state = {"url": "http://localhost:3000/", "standalone_url": "http://localhost:3001/",
                "stop_file": str(task_dir / "stop"), "synthetic_only": True,
                # 预置数据不调用模型；真实语音由用户操作触发，启动快照不是实时用量账本。
                "external_model_calls": None if args.voice_provider == 'doubao' else 0,
                "external_text_model_calls": 0, "external_voice_calls_in_seed": 0,
                "voice_calls_on_demand": args.voice_provider == 'doubao',
                "existing_build_reused": True, "frontend_port": 3100, "backend_port": 8000,
                "extended_history": args.extended_history, "seed_notes": args.seed_notes,
                "seed_history_states": args.seed_history_states, "seed_plan_history": args.seed_plan_history,
                "plan_history_url": plan_history_url,
                "voice_provider": args.voice_provider,
                "test_mail_url":'http://localhost:8025/' if args.local_mail else None,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=args.preview_minutes)).isoformat()}
            state_path = ROOT / "docs/logs/2026-10-24/native-home/integrated-preview.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(state, ensure_ascii=True), flush=True)
            deadline = time.monotonic() + args.preview_minutes * 60
            while time.monotonic() < deadline and not (task_dir / "stop").exists():
                if frontend.poll() is not None:
                    raise RuntimeError("练习室进程已停止")
                time.sleep(.2)
        finally:
            for server in mail_servers:server.shutdown();server.server_close()
            if gateway:
                gateway.shutdown()
                gateway.server_close()
            if frontend is not None and frontend.poll() is None:
                frontend.terminate()
                try:
                    frontend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    frontend.kill(); frontend.wait(timeout=5)
            backend.stop()


if __name__ == "__main__":
    main()
