"""JobRun — the backbone of the persistent task system (PLAN 2.Background tasks).

A JobRun is a single row in SQLite. The API process enqueues jobs; a Worker
process (or the API itself) claims them via a lease, records checkpoints, and
retries on failure. Because all state is in SQLite, a crashed worker can be
recovered by another worker or on restart (no Redis/Docker needed).
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import JobStatus, JobType, PKMixin, TimestampMixin


class JobRun(Base, PKMixin, TimestampMixin):
    __tablename__ = "job_runs"

    job_type: Mapped[str] = mapped_column(String(16), index=True)  # parse|index|reindex|delete|eval
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    progress: Mapped[float] = mapped_column(default=0.0)  # 0.0 - 1.0

    # --- Lease (租约) ---
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Checkpoint / retry ---
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)  # resumable state
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Timing ---
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict)
