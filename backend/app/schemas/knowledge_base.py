"""Pydantic schemas for KnowledgeBase."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    embedding_model: str = "Qwen3-Embedding-0.6B"
    reranker_model: str = "Qwen3-Reranker-0.6B"
    vision_enabled: bool = False
    settings: dict = Field(default_factory=dict)
    department_id: str | None = None
    access_scope: str = Field(default="department", pattern=r"^(department|restricted)$")


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    embedding_model: str | None = None
    reranker_model: str | None = None
    vision_enabled: bool | None = None
    settings: dict | None = None
    department_id: str | None = None
    access_scope: str | None = Field(default=None, pattern=r"^(department|restricted)$")


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    embedding_model: str
    reranker_model: str
    vision_enabled: bool
    current_generation: int
    settings: dict
    created_at: datetime
    updated_at: datetime
    document_count: int = 0  # populated by router
    department_id: str = ""
    department_name: str = ""
    access_scope: str = "department"
    access_level: str = "viewer"
