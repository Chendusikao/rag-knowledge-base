"""Shared model mixins + enums.

Centralizes the primary-key convention (`<prefix>_<hex>`) and timestamp columns
so every core object stays consistent across the single SQLite file.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


class PKMixin:
    """String primary key.

    Defaults to a UUID hex when not explicitly provided (used by internal rows
    like Chunk / Message). Public entities (KB, Document, Job, ...) pass a
    prefixed id via app.utils.id for readability in logs/traces.
    """

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EnumMixin:
    """Placeholder for shared enum helpers (kept simple for the scaffold)."""


# ---- Status / type enums (as string constants for SQLite portability) ----
class DocStatus:
    PENDING = "pending"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class JobType:
    PARSE = "parse"
    INDEX = "index"
    REINDEX = "reindex"
    DELETE = "delete"
    EVAL = "eval"


class RetrievalMode:
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


class Modality:
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"


class CitationType:
    PAGE = "page"
    SECTION = "section"
    TABLE = "table"
    IMAGE = "image"


class EvalType:
    FACT = "fact"
    MULTIHOP = "multihop"
    TABLE = "table"
    KEYWORD = "keyword"
    UNANSWERABLE = "unanswerable"


class ProviderRole:
    LLM = "llm"
    EMBEDDING = "embedding"
    VISION = "vision"
    AGENT = "agent"


class ProviderKind:
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"
    DIFY = "dify"
