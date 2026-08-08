"""Chunk (PLAN core object).

Structured chunk metadata: knowledge base, document version, section path, page
number, modality, region bbox, content hash, parser version, token estimate,
index generation.
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import Modality, PKMixin, TimestampMixin


class Chunk(Base, PKMixin, TimestampMixin):
    __tablename__ = "chunks"

    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    section_path: Mapped[list] = mapped_column(JSON, default=list)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    modality: Mapped[str] = mapped_column(String(16), default=Modality.TEXT)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_section: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(32), default="")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)  # 所属索引代次


from sqlalchemy import Index  # noqa: E402

Index("ix_chunks_kb_generation", Chunk.kb_id, Chunk.generation)
Index("ix_chunks_doc_modality", Chunk.doc_id, Chunk.modality)
