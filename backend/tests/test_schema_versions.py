from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, inspect, text
from app import schema_versions as versions
from tests.test_migrations import _legacy_engine, INTERVIEW_ID


def test_status_does_not_create_missing_database(tmp_path):
    path = tmp_path / 'not-created.sqlite3'
    engine = create_engine('sqlite:///' + path.as_posix())
    assert versions.schema_status(engine)['pending']
    assert not path.exists()
    engine.dispose()


def test_upgrades_are_serialized_and_repeatable(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'schema.sqlite3').as_posix(), connect_args={'timeout': 30})
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: versions.upgrade_schema(engine), range(2)))
    status = versions.schema_status(engine)
    assert status['applied'] == [v for v, _ in versions.MIGRATIONS]
    assert status['pending'] == status['unknown'] == []
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO account(id,username,password_hash) VALUES ('kept','kept','hash')"))
    versions.upgrade_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM account WHERE id='kept'")).scalar_one() == 'kept'
    engine.dispose()


def test_failed_upgrade_rolls_back_changes_and_stamps(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + (tmp_path / 'rollback.sqlite3').as_posix())
    def broken(connection):
        connection.execute(text('CREATE TABLE should_rollback (id INTEGER)'))
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(versions, 'MIGRATIONS', (('001_broken', broken),))
    with pytest.raises(RuntimeError, match='synthetic'):
        versions.upgrade_schema(engine)
    assert not inspect(engine).has_table('should_rollback')
    assert versions.schema_status(engine)['applied'] == []
    engine.dispose()


def test_unknown_newer_version_refuses_upgrade(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'newer.sqlite3').as_posix())
    versions.upgrade_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO schema_migration(version) VALUES ('999_future')"))
    with pytest.raises(RuntimeError, match='newer'):
        versions.upgrade_schema(engine)
    assert '999_future' in versions.schema_status(engine)['unknown']
    engine.dispose()


def test_versioned_runner_upgrades_legacy_rows_without_data_loss(tmp_path):
    engine = _legacy_engine(tmp_path)
    versions.upgrade_schema(engine)
    assert next(c for c in inspect(engine).get_columns('interview') if c['name']=='user_id')['nullable']
    with engine.connect() as connection:
        assert connection.execute(text('SELECT id FROM interview')).scalar_one() == INTERVIEW_ID
    assert versions.schema_status(engine)['pending'] == []
    engine.dispose()


def test_current_upgrade_adds_forum_to_existing_database(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'before-forum.sqlite3').as_posix())
    versions.upgrade_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO account(id,username,password_hash) VALUES ('kept','kept','hash')"))
        for table in reversed(versions.Base.metadata.sorted_tables):
            if table.name.startswith('forum_'):
                table.drop(connection)
        connection.execute(text("DELETE FROM schema_migration WHERE version='007_forum'"))
    assert versions.schema_status(engine)['pending'] == ['007_forum']
    versions.upgrade_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM account WHERE id='kept'")).scalar_one() == 'kept'
        assert connection.execute(text("SELECT count(*) FROM forum_post")).scalar_one() == 0
        assert versions.schema_status(engine)['pending'] == []
    engine.dispose()
