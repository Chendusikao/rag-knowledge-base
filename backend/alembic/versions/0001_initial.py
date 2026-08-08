"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-07

Creates all core tables for the V1 scaffold. Driven by Base.metadata so the
schema stays in sync with the SQLAlchemy models in app/models.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

from app.db.base import Base  # noqa: F401
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
