"""ChatSession, Message, Citation, RetrievalTrace.

Covers PLAN core objects: ChatSession, Message, Citation, RetrievalTrace.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import CitationType, PKMixin, TimestampMixin


class ChatSession(Base, PKMixin, TimestampMixin):
    __tablename__ = "chat_sessions"

    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    # Snapshot of provider config used (not secrets).
    backend: Mapped[str] = mapped_column(String(32), default="local")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base, PKMixin, TimestampMixin):
    __tablename__ = "messages"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Answer-level fields (PLAN 3.Online output structure).
    confidence: Mapped[float] = mapped_column(default=0.0)
    insufficient_evidence: Mapped[bool] = mapped_column(default=False)
    # Whether the message's source document has been deleted (PLAN 2.Offline).
    source_deleted: Mapped[bool] = mapped_column(default=False)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )
    trace: Mapped["RetrievalTrace | None"] = relationship(
        back_populates="message", cascade="all, delete-orphan", uselist=False
    )


class Citation(Base, PKMixin, TimestampMixin):
    """Clickable citation that locates a source chunk / page / section / table / image."""

    __tablename__ = "citations"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_name: Mapped[str] = mapped_column(String(512), default="")
    citation_type: Mapped[str] = mapped_column(String(16), default=CitationType.PAGE)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    section_path: Mapped[list] = mapped_column(JSON, default=list)
    region: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # bbox
    snippet: Mapped[str] = mapped_column(Text, default="")

    message: Mapped["Message"] = relationship(back_populates="citations")


class RetrievalTrace(Base, PKMixin, TimestampMixin):
    """Per-query retrieval diagnostics for the retrieval lab + tracing (PLAN)."""

    __tablename__ = "retrieval_traces"

    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="balanced")
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_queries: Mapped[list] = mapped_column(JSON, default=list)
    dense_rank: Mapped[list] = mapped_column(JSON, default=list)   # [{chunk_id, score}]
    bm25_rank: Mapped[list] = mapped_column(JSON, default=list)
    rrf_scores: Mapped[list] = mapped_column(JSON, default=list)
    rerank_scores: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    message: Mapped["Message"] = relationship(back_populates="trace")
