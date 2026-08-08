"""ProviderProfile — capability + credential *reference* (never the secret).

PLAN 3: "API 密钥使用 Windows Credential Manager 保存，SQLite 只记录凭据引用和能力信息。"
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import PKMixin, ProviderKind, ProviderRole, TimestampMixin


class ProviderProfile(Base, PKMixin, TimestampMixin):
    __tablename__ = "provider_profiles"

    # role: llm | embedding | vision | agent  (PLAN 3 "PUT /provider-profiles/{role}")
    role: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    kind: Mapped[str] = mapped_column(String(32), default=ProviderKind.MOCK)
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    # Reference to the secret stored in Windows Credential Manager (NOT the secret).
    credential_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"rerank": true}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
