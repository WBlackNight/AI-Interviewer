"""Ordered, transactional schema upgrades with database-scoped startup locking."""
from sqlalchemy import inspect, text
from pathlib import Path
from app.migrations import upgrade_interview_user_nullable, upgrade_event_sequences
from app.models.entities import Base
from app.models import forum


def add_goals_and_shares(connection):
    for name in ("preparation_goal", "report_share"):
        Base.metadata.tables[name].create(connection, checkfirst=True)

def add_account_details(connection):
    Base.metadata.tables["account_details"].create(connection, checkfirst=True)


def add_assistant(connection):
    Base.metadata.tables["assistant_conversation"].create(connection, checkfirst=True)


def add_admin_operations(connection):
    for name in ('admin_audit', 'admin_question_review'):
        Base.metadata.tables[name].create(connection, checkfirst=True)


def add_forum(connection):
    for model in (forum.ForumProfile, forum.ForumIdentityChange, forum.ForumPost,
                  forum.ForumComment, forum.ForumLike, forum.ForumBookmark, forum.ForumReport):
        model.__table__.create(connection, checkfirst=True)


MIGRATIONS = (
    ('001_interview_nullable', upgrade_interview_user_nullable),
    ('002_event_sequences', upgrade_event_sequences),
    ('003_goals_and_shares', add_goals_and_shares),
    ('004_account_details', add_account_details),
    ('005_assistant', add_assistant),
    ('006_admin_operations', add_admin_operations),
    ('007_forum', add_forum),
)


def schema_status(engine):
    known = [version for version, _ in MIGRATIONS]
    database = engine.url.database
    if engine.dialect.name == 'sqlite' and database and database != ':memory:' and not Path(database).exists():
        return {'applied': [], 'pending': known, 'unknown': []}
    with engine.connect() as connection:
        applied = (list(connection.execute(text('SELECT version FROM schema_migration ORDER BY version')).scalars())
                   if inspect(connection).has_table('schema_migration') else [])
    return {'applied': applied, 'pending': [v for v in known if v not in applied],
            'unknown': [v for v in applied if v not in known]}


def upgrade_schema(engine):
    """Serialize upgrades; stamp only when all changes commit successfully."""
    with engine.connect() as connection:
        try:
            if engine.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            elif engine.dialect.name == 'postgresql':
                connection.begin()
                connection.execute(text('SELECT pg_advisory_xact_lock(69331281)'))
            else:
                raise RuntimeError('Unsupported migration database')
            connection.execute(text('CREATE TABLE IF NOT EXISTS schema_migration '
                '(version VARCHAR(64) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)'))
            applied = set(connection.execute(text('SELECT version FROM schema_migration')).scalars())
            known = {version for version, _ in MIGRATIONS}
            if applied - known:
                raise RuntimeError('Database schema is newer than this application; refusing to downgrade')
            Base.metadata.create_all(connection)
            for version, migrate in MIGRATIONS:
                if version not in applied:
                    migrate(connection)
                    connection.execute(text('INSERT INTO schema_migration (version) VALUES (:version)'), {'version': version})
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
