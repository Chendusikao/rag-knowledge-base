"""Async SQLAlchemy engine + session factory.

Uses SQLite in WAL mode (PLAN: "SQLite WAL 保存业务状态..."). The `mode=rwc`
query param creates the file if missing. WAL enables concurrent readers with a
writer and is required for the persistent task system.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# 每个 session 使用独立连接（默认队列池）。⚠️ 之前用 StaticPool（全应用单连接），
# 会导致并发场景数据竞争：lifespan 里的任务 worker 每 2s 轮询（claim_job 会
# commit），在 DeepSeek 流式回答挂起几十秒期间，worker 用同一连接提交/回滚事务，
# 会把 chat 事务里刚 flush 的 chat_sessions 一起挤掉，随后 INSERT messages 报
# FOREIGN KEY constraint failed。改用独立连接后 worker 与 chat 互不干扰。
# WAL 模式 + busy_timeout 已能处理偶发的 SQLite 写锁冲突（空闲 worker 只读）。
_engine = create_async_engine(
    settings.sqlite_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Apply WAL + busy timeout whenever a connection is made.
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(_engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.close()


AsyncSessionLocal = async_sessionmaker(
    bind=_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_engine():
    return _engine
