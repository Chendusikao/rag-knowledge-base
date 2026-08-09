"""Retrieval inspect endpoint (PLAN 3: POST /api/v1/retrieval/inspect)."""
from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session as _gs
from app.models.enterprise import EnterpriseUser
from app.schemas.retrieval import (
    RetrievalInspectRequest,
    RetrievalInspectResponse,
    RetrievedChunk,
)
from app.services.retrieval.manager import retrieve
from app.services.enterprise import require_kb_access

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


@router.post("/retrieval/inspect", response_model=RetrievalInspectResponse)
async def retrieval_inspect(
    req: RetrievalInspectRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> RetrievalInspectResponse:
    await require_kb_access(session, user, req.kb_id, "manager", request=request)
    result = await retrieve(
        session, req.kb_id, req.query, mode=req.mode, filters=req.filters,
        force_refresh=req.force_refresh,
    )
    results = [
        RetrievedChunk(
            chunk_id=r.chunk_id, doc_id=r.doc_id, doc_name=r.doc_name,
            page_number=r.page_number, section_path=r.section_path,
            modality=r.modality, snippet=r.snippet,
            dense_score=r.dense_score, bm25_score=r.bm25_score,
            rrf_score=r.rrf_score, rerank_score=r.rerank_score,
        )
        for r in result.results
    ]
    return RetrievalInspectResponse(
        query=result.query, mode=result.mode,
        rewritten_queries=result.rewritten_queries, results=results,
        dense_rank=result.dense_rank, bm25_rank=result.bm25_rank,
        rrf_scores=result.rrf_scores, rerank_scores=result.rerank_scores,
        latency_ms=result.latency_ms, cache_hit=result.cache_hit,
    )
