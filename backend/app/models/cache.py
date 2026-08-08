"""CacheEntry — tiered cache (parse / embedding / retrieval / rerank).

PLAN 2 "增量索引与缓存": versioned cache keys; natural invalidation on
doc/model/prompt/index version change; no fuzzy cache flushing.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import PKMixin


class CacheEntry(Base, PKMixin):
    __tablename__ = "cache_entries"

    namespace: Mapped[str] = mapped_column(String(32), index=True)  # parse|embedding|retrieval|rerank
    cache_key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    hit_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("namespace", "cache_key", name="uq_cache_ns_key"),)
