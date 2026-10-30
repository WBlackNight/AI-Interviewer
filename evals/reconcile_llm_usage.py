"""运维核账：先停旧worker并核实供应商累计用量，再更新未知/遗留pending。

必须从backend目录运行，确保DATABASE_URL/.env与服务一致。不会创建或迁移数据库。
参数为资源累计值，不能降低已知用量；version从受保护usage接口或运维查询获取。
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import SessionLocal
from app.llm.persistent_budget import reconcile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["interview","resume"], required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--total-tokens", type=int, required=True)
    parser.add_argument("--total-cost", type=float, required=True)
    parser.add_argument("--verified-provider-usage", action="store_true", required=True)
    args = parser.parse_args()
    try:
        reconcile(SessionLocal, args.kind, args.id, version=args.version,
                  total_tokens=args.total_tokens, total_cost=args.total_cost)
    except Exception as exc:
        print("reconcile_failed category=" + type(exc).__name__)
        return 1
    print("reconcile_completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
