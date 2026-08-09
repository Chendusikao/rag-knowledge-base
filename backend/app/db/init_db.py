"""Database initialization: create all tables (and a baseline Alembic stamp).

For the scaffold we create tables directly via metadata; Alembic is configured for
incremental migrations once real schema changes land.
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.base import Base
from app.db.session import get_engine


async def init_db() -> None:
    # Import models so they register on Base.metadata before create_all.
    from app import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure WAL is on for the freshly created DB.
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        # Audit rows are append-only even when a caller bypasses the API layer.
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit events are immutable');
            END;
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit events are immutable');
            END;
        """))
