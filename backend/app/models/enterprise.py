"""Enterprise organization, authentication, authorization and audit models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import (
    KnowledgeAccessLevel,
    KnowledgeAccessScope,
    PKMixin,
    SystemRole,
    TimestampMixin,
)


DEFAULT_DEPARTMENT_ID = "dept_company"


class Department(Base, PKMixin, TimestampMixin):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class EnterpriseUser(Base, PKMixin, TimestampMixin):
    __tablename__ = "enterprise_users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    system_role: Mapped[str] = mapped_column(String(32), default=SystemRole.MEMBER, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthSession(Base, PKMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("enterprise_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class KnowledgeBaseScope(Base, PKMixin, TimestampMixin):
    """Enterprise metadata kept separate so existing KB rows need no destructive migration."""

    __tablename__ = "knowledge_base_scopes"

    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    access_scope: Mapped[str] = mapped_column(
        String(24), default=KnowledgeAccessScope.DEPARTMENT, index=True
    )


class KnowledgeBasePermission(Base, PKMixin, TimestampMixin):
    __tablename__ = "knowledge_base_permissions"
    __table_args__ = (UniqueConstraint("kb_id", "user_id", name="uq_kb_permission_user"),)

    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("enterprise_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    access_level: Mapped[str] = mapped_column(
        String(16), default=KnowledgeAccessLevel.VIEWER, index=True
    )
    granted_by: Mapped[str | None] = mapped_column(
        ForeignKey("enterprise_users.id", ondelete="SET NULL"), nullable=True
    )


class AuditEvent(Base, PKMixin):
    """Append-only event. DB triggers reject UPDATE and DELETE operations."""

    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(320), default="")
    action: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    department_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success", index=True)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
