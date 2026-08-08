"""Pydantic schemas for retrieval inspect (retrieval lab + tracing)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalInspectRequest(BaseModel):
    kb_id: str
    query: str = Field(min_length=1)
    mode: str = "balanced"  # fast | balanced | deep
    filters: dict = Field(default_factory=dict)
    force_refresh: bool = False


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str = ""
    page_number: int = 0
    section_path: list = Field(default_factory=list)
    modality: str = "text"
    snippet: str = ""
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


class RetrievalInspectResponse(BaseModel):
    query: str
    mode: str
    rewritten_queries: list[str] = Field(default_factory=list)
    results: list[RetrievedChunk] = Field(default_factory=list)
    dense_rank: list[dict] = Field(default_factory=list)
    bm25_rank: list[dict] = Field(default_factory=list)
    rrf_scores: list[dict] = Field(default_factory=list)
    rerank_scores: list[dict] = Field(default_factory=list)
    latency_ms: int = 0
    cache_hit: bool = False
