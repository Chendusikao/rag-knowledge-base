"""Declarative base for all SQLAlchemy models.

All core objects (KnowledgeBase, Document, Chunk, JobRun, ChatSession, Evaluation*,
ProviderProfile, CacheEntry) share this Base so they live in one SQLite file.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base for the whole project."""

    # Provides a `id` column convention helper via mixins (see models).
    pass
