"""Start the same-origin application with a stable working directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def server_environment(database=None, offline=False):
    environment = os.environ.copy()
    if database is not None:
        from sqlalchemy.engine import URL
        environment["DATABASE_URL"] = URL.create("sqlite", database=str(database.resolve())).render_as_string()
    if offline:
        environment.update({
            "LLM_API_KEY": "",
            "JUDGE0_URL": "",
            "VOICE_ENABLED": "false",
            "MAIL_MODE": "disabled",
            "RETRIEVAL_PROVIDER": "bm25",
            "EMBEDDING_PROVIDER": "hash",
        })
    return environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--database", type=Path, help="SQLite file, relative to the caller's directory")
    parser.add_argument("--offline", action="store_true", help="Disable remote model, voice, mail and sandbox services")
    parser.add_argument("--reload", action="store_true", help="Reload source changes during local development")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    if args.database:
        database = args.database.resolve()
        if not database.parent.is_dir() or database.is_dir():
            parser.error("Database must be a file in an existing directory")
    command = [sys.executable, "-m", "uvicorn", "app.main:app",
               "--host", args.host, "--port", str(args.port), "--workers", "1"]
    if args.reload:
        command.append("--reload")
    try:
        return subprocess.call(command, cwd=BACKEND,
                               env=server_environment(args.database, args.offline))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
