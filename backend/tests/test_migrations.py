"""迁移测试：interview.user_id 可空性升级。

背景：模型已支持匿名面试（``user_id`` 可空），但 ``create_all`` **不会演进已有列**，
因此所有在改动之前创建的库都会在创建面试时报
``NOT NULL constraint failed: interview.user_id``（HTTP 500）。

这些用例用"先把库降级成旧 schema、再跑迁移"的方式构造真实场景，
而不是只测一个空库——空库由 create_all 直接建对，测不出问题。
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, create_engine, inspect, text

from app.migrations import upgrade_interview_user_nullable
from app.models.entities import Base, Interview

USER_ID = "u" * 32
INTERVIEW_ID = "i" * 32

#: 冻结的旧 schema（history）：user_id 为 NOT NULL。
#: 刻意不复用模型定义——它就是"过去的样子"，不应随模型演进。
LEGACY_INTERVIEW = (
    "CREATE TABLE interview ("
    "id VARCHAR(32) NOT NULL, "
    "user_id VARCHAR(32) NOT NULL, "
    "resume_id VARCHAR(32), "
    "position VARCHAR(64) NOT NULL, "
    "difficulty VARCHAR(16) NOT NULL, "
    '"plan" JSON NOT NULL, '
    "status VARCHAR(16) NOT NULL, "
    "started_at DATETIME, "
    "ended_at DATETIME, "
    "PRIMARY KEY (id), "
    "FOREIGN KEY(user_id) REFERENCES user (id), "
    "FOREIGN KEY(resume_id) REFERENCES resume (id))"
)


def _legacy_engine(tmp_path):
    """构造一个"当前 schema、但 interview 表仍是旧样子"的库，并写入历史数据。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'legacy.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        # 降级为旧 schema（外键在 SQLite 默认关闭，可安全重建）
        connection.execute(text("DROP TABLE interview"))
        connection.execute(text(LEGACY_INTERVIEW))
        connection.execute(text(
            "CREATE INDEX ix_interview_user_id ON interview (user_id)"
        ))
        connection.execute(text(
            "INSERT INTO user (id, name) VALUES (:uid, '旧用户')"
        ), {"uid": USER_ID})
        connection.execute(text(
            "INSERT INTO interview (id, user_id, resume_id, position, difficulty, plan, status) "
            "VALUES (:iid, :uid, NULL, 'java_backend', 'mid', '[]', 'created')"
        ), {"iid": INTERVIEW_ID, "uid": USER_ID})
    return engine


def _nullable(engine) -> bool:
    columns = {c["name"]: c for c in inspect(engine).get_columns("interview")}
    return bool(columns["user_id"].get("nullable"))


def _index_names(engine) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes("interview")}


class TestInterviewUserNullableUpgrade:
    def test_makes_column_nullable_and_keeps_data(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        assert _nullable(engine) is False, "前置条件：旧库应为 NOT NULL"

        assert upgrade_interview_user_nullable(engine) is True

        assert _nullable(engine) is True
        with engine.begin() as connection:
            row = connection.execute(text(
                "SELECT user_id, position FROM interview WHERE id = :iid"
            ), {"iid": INTERVIEW_ID}).one()
        assert row[0] == USER_ID, "历史行的 user_id 必须保留"
        assert row[1] == "java_backend"
        engine.dispose()

    def test_anonymous_interview_insert_works_after_upgrade(self, tmp_path):
        """核心目的：升级后能创建 user_id 为 NULL 的面试。"""
        engine = _legacy_engine(tmp_path)
        upgrade_interview_user_nullable(engine)
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO interview (id, user_id, resume_id, position, difficulty, plan, status) "
                "VALUES (:iid, NULL, NULL, 'java_backend', 'mid', '[]', 'created')"
            ), {"iid": "a" * 32})
            count = connection.execute(text(
                "SELECT COUNT(*) FROM interview WHERE user_id IS NULL"
            )).scalar_one()
        assert count == 1
        engine.dispose()

    def test_indexes_are_rebuilt(self, tmp_path):
        """DROP TABLE 会连带删掉旧索引，必须重建，否则查询计划退化。"""
        engine = _legacy_engine(tmp_path)
        before = _index_names(engine)
        upgrade_interview_user_nullable(engine)
        after = _index_names(engine)
        assert "ix_interview_user_id" in after, f"重建后索引缺失：{before} -> {after}"
        engine.dispose()

    def test_idempotent(self, tmp_path):
        """main.py 每次启动都会调用，重复执行必须是 no-op。"""
        engine = _legacy_engine(tmp_path)
        assert upgrade_interview_user_nullable(engine) is True
        assert upgrade_interview_user_nullable(engine) is False
        with engine.begin() as connection:
            assert connection.execute(text(
                "SELECT COUNT(*) FROM interview"
            )).scalar_one() == 1
        engine.dispose()

    def test_skips_when_already_current_schema(self, tmp_path):
        """全新库由 create_all 建对，迁移应直接跳过。"""
        engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
        Base.metadata.create_all(engine)
        assert upgrade_interview_user_nullable(engine) is False
        engine.dispose()

    def test_skips_when_table_missing(self, tmp_path):
        """空库（尚未建表）不能报错，否则启动就挂。"""
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        assert upgrade_interview_user_nullable(engine) is False
        engine.dispose()

    def test_leaves_no_temp_table_behind(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        upgrade_interview_user_nullable(engine)
        with engine.begin() as connection:
            # 用精确表名：LIKE 里 "_" 是单字符通配符，'interview__%' 会误匹配
            # interview_event / interview_runtime 等表。
            leftovers = connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name = 'interview__migration_new'"
            )).fetchall()
        assert leftovers == [], leftovers
        engine.dispose()

    def test_recovers_from_leftover_temp_table(self, tmp_path):
        """上次中断可能留下临时表；重跑必须能自愈而不是报错。"""
        engine = _legacy_engine(tmp_path)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE interview__migration_new (id VARCHAR(32))"))
        assert upgrade_interview_user_nullable(engine) is True
        assert _nullable(engine) is True
        engine.dispose()

    def test_orm_insert_without_user_succeeds(self, tmp_path):
        """端到端语义：ORM 插入匿名面试不再触发 NOT NULL。"""
        engine = _legacy_engine(tmp_path)
        upgrade_interview_user_nullable(engine)
        with engine.begin() as connection:
            connection.execute(Interview.__table__.insert().values(
                id=str(uuid.uuid4().hex), user_id=None, resume_id=None,
                position="java_backend", difficulty="mid", plan=[], status="created",
            ))
            assert connection.execute(text(
                "SELECT COUNT(*) FROM interview WHERE user_id IS NULL"
            )).scalar_one() == 1
        engine.dispose()
