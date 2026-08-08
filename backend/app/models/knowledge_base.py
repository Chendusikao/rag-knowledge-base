"""KnowledgeBase + IndexGeneration (PLAN core objects).

Document / DocumentVersion live in document.py and Chunk in chunk.py to keep
import boundaries clean (chat/indexing/retrieval import them directly).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import PKMixin, TimestampMixin


class KnowledgeBase(Base, PKMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(128), default="Qwen3-Embedding-0.6B")
    reranker_model: Mapped[str] = mapped_column(String(128), default="Qwen3-Reranker-0.6B")
    vision_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    current_generation: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    documents: Mapped[list] = relationship(
        "Document", back_populates="kb", cascade="all, delete-orphan"
    )


class IndexGeneration(Base, PKMixin, TimestampMixin):
    """Tracks an atomic index build for a KB (PLAN: 原子切换)."""

    __tablename__ = "index_generations"

    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="building")  # building|active|failed
    dense_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    bm25_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
