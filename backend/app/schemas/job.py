"""Pydantic schema for JobRun (status polling)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    kb_id: str
    doc_id: str | None = None
    status: str
    progress: float
    retries: int
    max_retries: int
    error: str | None = None
    checkpoint: dict
    lease_owner: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
