"""Pydantic schemas for Document."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    filename: str
    mime_type: str
    ext: str
    content_hash: str
    size_bytes: int
    num_pages: int
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    """Returned immediately after an upload; indexing runs as a JobRun."""

    document: DocumentOut
    job_id: str
    message: str = "Document accepted; indexing job queued."
