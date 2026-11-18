import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from backup_database import backup


def test_online_backup_and_existing_target_protection(tmp_path):
    source = tmp_path / 'source.sqlite3'
    target = tmp_path / 'backup.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE records (value TEXT)')
        db.execute('INSERT INTO records VALUES (?)', ('saved',))
        db.commit()
        backup(source, target)
    with sqlite3.connect(target) as copy:
        assert copy.execute('SELECT value FROM records').fetchone() == ('saved',)
    with pytest.raises(FileExistsError):
        backup(source, target)
    with pytest.raises(ValueError):
        backup(source, source)


def test_failed_backup_does_not_leave_partial_file(tmp_path):
    source = tmp_path / 'invalid.sqlite3'
    source.write_text('not a database')
    target = tmp_path / 'backup.sqlite3'
    with pytest.raises(sqlite3.DatabaseError):
        backup(source, target)
    assert not target.exists()
