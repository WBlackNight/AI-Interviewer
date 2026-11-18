from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'evals'))
from native_home_preview import preview_database


def test_persistent_preview_reuses_database_without_reseeding(tmp_path):
    backend = tmp_path / 'backend'
    backend.mkdir()
    task = backend / 'temporary'
    task.mkdir()
    path, existing = preview_database(backend, task, True, False)
    assert path == backend / 'preview-data.sqlite3' and not existing
    with pytest.raises(ValueError, match='种子'):
        preview_database(backend, task, True, True)
    path.write_bytes(b'existing data')
    same, existing = preview_database(backend, task, True, False)
    assert same.read_bytes() == b'existing data' and existing
    with pytest.raises(ValueError, match='种子'):
        preview_database(backend, task, True, True)
    assert preview_database(backend, task, False, True) == (task / 'preview.sqlite3', False)
