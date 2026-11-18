"""Portability regressions for the root-independent launch command."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

SOURCE = Path(__file__).resolve().parents[2] / "tools/run_server.py"
spec = importlib.util.spec_from_file_location("server_launcher", SOURCE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_database_override_is_absolute_and_offline_does_not_mutate_parent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "synthetic-key")
    result = launcher.server_environment(Path("demo with spaces.sqlite3"), offline=True)
    assert Path(make_url(result["DATABASE_URL"]).database) == tmp_path / "demo with spaces.sqlite3"
    assert not (tmp_path / "demo with spaces.sqlite3").exists()
    assert result["LLM_API_KEY"] == "" and result["VOICE_ENABLED"] == "false"
    assert result["MAIL_MODE"] == "disabled" and result["RETRIEVAL_PROVIDER"] == "bm25"
    assert launcher.os.environ["LLM_API_KEY"] == "synthetic-key"


def test_launcher_keeps_backend_working_directory_from_any_caller(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(launcher.subprocess, "call", lambda command, **kwargs: calls.append((command, kwargs)) or 0)
    assert launcher.main(["--offline", "--database", "demo.sqlite3", "--port", "3210"]) == 0
    command, options = calls[0]
    assert command[:4] == [launcher.sys.executable, "-m", "uvicorn", "app.main:app"]
    assert command[command.index("--port") + 1] == "3210"
    assert options["cwd"] == launcher.BACKEND


def test_invalid_launcher_paths_and_ports_do_not_start_process(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.subprocess, "call", lambda *args, **kwargs: pytest.fail("must not launch"))
    with pytest.raises(SystemExit):
        launcher.main(["--port", "0"])
    with pytest.raises(SystemExit):
        launcher.main(["--database", str(tmp_path / "missing-parent" / "data.sqlite3")])
