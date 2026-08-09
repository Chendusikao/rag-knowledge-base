"""enterprise departments, authentication, permissions and audit

Revision ID: 0002_enterprise_governance
Revises: 0001_initial
Create Date: 2026-08-09

The enterprise metadata lives in new tables so upgrading an existing local
knowledge base does not rebuild or rewrite the core document tables.
"""
from alembic import op
from sqlalchemy import text

from app import models  # noqa: F401
from app.db.base import Base
from app.models.enterprise import DEFAULT_DEPARTMENT_ID

revision = "0002_enterprise_governance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_TABLES = [
    "departments",
    "enterprise_users",
    "auth_sessions",
    "knowledge_base_scopes",
    "knowledge_base_permissions",
    "audit_events",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in _TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

    bind.execute(
        text(
            """
            INSERT OR IGNORE INTO departments
                (id, name, code, description, is_active, created_at, updated_at)
            VALUES
                (:id, '公司公共', 'company', '企业默认部门，用于承接升级前已有的知识库。', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {"id": DEFAULT_DEPARTMENT_ID},
    )
    bind.execute(
        text(
            """
            INSERT OR IGNORE INTO knowledge_base_scopes
                (id, kb_id, department_id, access_scope, created_at, updated_at)
            SELECT
                'scope_' || lower(hex(randomblob(16))), id, :department_id,
                'department', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM knowledge_bases
            """
        ),
        {"department_id": DEFAULT_DEPARTMENT_ID},
    )
    bind.execute(text("""
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit events are immutable');
        END;
    """))
    bind.execute(text("""
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit events are immutable');
        END;
    """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP TRIGGER IF EXISTS audit_events_no_delete"))
    bind.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update"))
    for table_name in reversed(_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
