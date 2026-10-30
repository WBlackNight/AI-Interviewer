"""增量升级：保留历史行。

两条升级路径，均在启动时执行且必须**幂等**（main.py 每次启动都会调用）：

- ``upgrade_event_sequences``：修复旧事件序号后添加唯一索引；
- ``upgrade_interview_user_nullable``：去掉 ``interview.user_id`` 的 NOT NULL，
  使"不带简历直接开始面试"（匿名面试）在旧库上也能工作。

为什么用迁移而不是"删库重建"：
1. ``create_all`` 只建缺失的表，**不会演进已有列**（这是 SQLAlchemy 的既定行为），
   所以模型改了可空性后，任何在改动之前创建的库都会在创建面试时报
   ``NOT NULL constraint failed: interview.user_id``（HTTP 500）；
2. 该问题**不是本机独有**——同事克隆、预发库、以及将来切到 PostgreSQL 的部署
   都会以同样方式失败，删本地 dev.db 只解决一台机器；
3. 迁移可以在测试里被验证（旧 schema → 升级 → 断言可空且数据保留），
   "删库"没有任何可回归的面，同一个坑会再踩一次。
"""
import logging

from sqlalchemy import MetaData, Table, func, inspect, select, text, update
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models.entities import Base, Interview, InterviewEvent

logger = logging.getLogger(__name__)

#: 重建期间使用的临时表名。取一个不可能与业务表重名的名字。
_REBUILD_TEMP_TABLE = "interview__migration_new"


def upgrade_event_sequences(engine):
    table = InterviewEvent.__table__
    with engine.begin() as connection:
        duplicates = connection.execute(select(table.c.interview_id).group_by(
            table.c.interview_id, table.c.seq).having(func.count() > 1)).scalars().all()
        for interview_id in set(duplicates):
            ids = connection.execute(select(table.c.id).where(
                table.c.interview_id == interview_id).order_by(table.c.id)).scalars().all()
            # 先进入临时负序号，避免已有索引的中间冲突；历史 payload 同步新序号。
            for row_id in ids:
                connection.execute(update(table).where(table.c.id == row_id).values(seq=-row_id-1))
            for seq, row_id in enumerate(ids):
                payload = connection.execute(select(table.c.payload).where(table.c.id == row_id)).scalar_one()
                connection.execute(update(table).where(table.c.id == row_id).values(
                    seq=seq, payload={**payload, "seq": seq}))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_interview_event_unique_seq "
                                "ON interview_event (interview_id, seq)"))
    if duplicates:
        logger.warning("已修复历史面试事件序号 interviews=%d", len(set(duplicates)))


def upgrade_interview_user_nullable(engine) -> bool:
    """允许匿名面试：去掉 ``interview.user_id`` 的 NOT NULL 约束。

    幂等：已是可空或表不存在时直接返回 False，不做任何写入。

    SQLite 不支持 ``ALTER COLUMN ... DROP NOT NULL``，因此按官方推荐的表重建流程：
    建新表 → 拷数据 → 删旧表 → 改名 → 重建索引，全程在一个事务内完成
    （失败即回滚，不会留下半成品）。PostgreSQL 用一条 ALTER 即可。

    ⚠️ 自动化测试只覆盖 SQLite 分支（本项目当前部署方式）；
    PostgreSQL 分支尚未在本环境实测。
    """
    inspector = inspect(engine)
    if "interview" not in inspector.get_table_names():
        return False  # 全新库：create_all 已按当前模型建好

    columns = {column["name"]: column for column in inspector.get_columns("interview")}
    current = columns.get("user_id")
    if current is None:
        logger.warning("interview 表缺少 user_id 列，跳过可空性升级")
        return False
    if current.get("nullable", False):
        return False  # 已升级

    if engine.dialect.name == "sqlite":
        _rebuild_interview_sqlite(engine)
    else:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE interview ALTER COLUMN user_id DROP NOT NULL"))

    logger.warning("已升级 interview.user_id 为可空（支持匿名面试）")
    return True


def _rebuilt_table() -> Table:
    """把模型整体复制一份，并把 ``interview`` 换成临时表名后返回。

    不能只复制 interview 一张表：它的外键指向 ``user`` / ``resume``，
    目标表不在同一个 MetaData 里就无法编译 DDL
    （会抛 ``NoReferencedTableError``）。按依赖顺序整体复制即可解决，
    且除 interview 外都不会真的建表——只借用它们的定义来解析外键。
    """
    metadata = MetaData()
    rebuilt: list[Table] = []
    for table in Base.metadata.sorted_tables:
        if table.name == Interview.__tablename__:
            rebuilt.append(table.to_metadata(metadata, name=_REBUILD_TEMP_TABLE))
        else:
            table.to_metadata(metadata)
    if not rebuilt:
        raise RuntimeError("模型中没有 interview 表，无法执行重建升级")
    return rebuilt[0]


def _rebuild_interview_sqlite(engine) -> None:
    """SQLite 表重建：保证数据、外键与索引都不丢。"""
    source = Interview.__table__
    column_list = ", ".join(f'"{column.name}"' for column in source.columns)
    create_ddl = str(CreateTable(_rebuilt_table()).compile(engine))

    with engine.begin() as connection:
        # 上一次中断可能留下临时表：先清掉，保证幂等。
        connection.execute(text(f'DROP TABLE IF EXISTS "{_REBUILD_TEMP_TABLE}"'))
        connection.execute(text(create_ddl))
        connection.execute(text(
            f'INSERT INTO "{_REBUILD_TEMP_TABLE}" ({column_list}) '
            f'SELECT {column_list} FROM interview'
        ))
        connection.execute(text("DROP TABLE interview"))
        connection.execute(text(f'ALTER TABLE "{_REBUILD_TEMP_TABLE}" RENAME TO interview'))
        # DROP TABLE 会连带删除旧索引，必须按模型定义重建。
        for index in source.indexes:
            connection.execute(text(str(CreateIndex(index).compile(engine))))

        # 外键完整性自检：重建表最容易出的问题是把引用关系弄丢。
        violations = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
        if violations:
            raise RuntimeError(
                f"表重建后外键校验失败（{len(violations)} 处），已回滚：{violations[:3]}"
            )
        rows = connection.execute(text("SELECT COUNT(*) FROM interview")).scalar_one()
    logger.info("interview 表已重建，保留 %d 行", rows)
