"""Pydantic schemas for chat + streaming + citations.

ChatRequest FIXED shape (PLAN 3):
    kb_id, session_id?, query, mode, filters, backend, force_refresh
Answer structure (PLAN 3.Online):
    answer, citations, confidence, insufficient_evidence
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RetrievalMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


class ChatRequest(BaseModel):
    kb_id: str
    session_id: str | None = None
    query: str = Field(min_length=1)
    mode: RetrievalMode = RetrievalMode.BALANCED
    filters: dict = Field(default_factory=dict)  # e.g. {"doc_id": "...", "modality": "table"}
    backend: str = "local"  # local | openai_compatible | dify
    force_refresh: bool = False


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_id: str | None = None
    kb_id: str
    doc_id: str
    doc_name: str = ""
    citation_type: str = "page"
    page_number: int = 0
    section_path: list = Field(default_factory=list)
    region: dict | None = None
    snippet: str = ""


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    confidence: float = 0.0
    insufficient_evidence: bool = False
    citations: list[CitationOut] = Field(default_factory=list)
    created_at: datetime


# ---- SSE streaming event envelope (PLAN: POST /chat/stream SSE 返回阶段/token/引用/结果) ----
class StreamPhase(str, Enum):
    RETRIEVE = "retrieve"
    RERANK = "rerank"
    GENERATE = "generate"
    CITATION = "citation"
    DONE = "done"
    ERROR = "error"


class ChatStreamEvent(BaseModel):
    phase: StreamPhase
    session_id: str | None = None
    message_id: str | None = None
    token: str | None = None          # incremental token during GENERATE
    citations: list[CitationOut] | None = None
    confidence: float | None = None
    insufficient_evidence: bool | None = None
    data: dict | None = None           # misc (e.g. trace id, latency)
    error: str | None = None
