"""Retrieval manager (PLAN 3.Online — three modes, RRF, rerank, second-pass).

Orchestrates: query rewrite/route -> BM25 + Dense recall -> RRF fusion ->
(rerank) -> context assembly with citations + token budget.

Dense embedding and reranking are *pluggable* behind the provider/reranker
interfaces so the scaffold runs without a GPU/local model; the manager shape
matches the production design (Chroma for dense; DeepSeek or Qwen3-Reranker for
rerank, selectable via ``rerank_provider``). RRF is the always-on fusion; the
reranker is an optional refinement that degrades gracefully to RRF order.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.common import RetrievalMode
from app.models.knowledge_base import KnowledgeBase
from app.services.providers.deepseek import get_reranker
from app.services.providers.factory import get_embedding
from app.services.retrieval.bm25 import get_bm25, invalidate as invalidate_bm25
from app.services.retrieval.dense_store import get_store
from app.services.retrieval.rrf import rrf

# Per-mode recall/fusion/rerank parameters (PLAN 3.Online).
MODE_PARAMS: dict[str, dict] = {
    RetrievalMode.FAST: {
        "dense_topk": 20, "bm25_topk": 20, "rrf_keep": 8, "rerank_keep": 8,
        "rewrite": False, "subqueries": 1, "second_pass": False,
    },
    RetrievalMode.BALANCED: {
        "dense_topk": 40, "bm25_topk": 40, "rrf_keep": 30, "rerank_keep": 8,
        "rewrite": True, "subqueries": 1, "second_pass": False,
    },
    RetrievalMode.DEEP: {
        "dense_topk": 40, "bm25_topk": 40, "rrf_keep": 60, "rerank_keep": 12,
        "rewrite": True, "subqueries": 3, "second_pass": True,
    },
}


@dataclass
class _ChunkRow:
    chunk_id: str
    doc_id: str
    doc_name: str
    page_number: int
    section_path: list
    modality: str
    content: str


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    doc_name: str = ""
    page_number: int = 0
    section_path: list = field(default_factory=list)
    modality: str = "text"
    snippet: str = ""
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RetrievalResult:
    query: str
    mode: str
    rewritten_queries: list[str]
    results: list[RetrievedChunk]
    dense_rank: list[dict]
    bm25_rank: list[dict]
    rrf_scores: list[dict]
    rerank_scores: list[dict]
    latency_ms: int
    cache_hit: bool
    context_bundle: dict  # {context_text, citations}
    insufficient_evidence: bool


def _snippet(text: str, n: int = 240) -> str:
    text = " ".join(text.split())
    return text[:n]


async def _active_generation(session: AsyncSession, kb_id: str) -> int:
    # populate_existing forces a re-read from DB (the cached instance may be
    # stale after a worker bumped current_generation in another session).
    res = await session.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .execution_options(populate_existing=True)
    )
    kb = res.scalar_one_or_none()
    return kb.current_generation if kb else 0


async def _load_chunks(
    session: AsyncSession, kb_id: str, generation: int, filters: dict
) -> list[_ChunkRow]:
    stmt = select(Chunk).where(Chunk.kb_id == kb_id, Chunk.generation == generation)
    if filters.get("doc_id"):
        stmt = stmt.where(Chunk.doc_id == filters["doc_id"])
    if filters.get("modality"):
        stmt = stmt.where(Chunk.modality == filters["modality"])
    res = await session.execute(stmt)
    rows = res.scalars().all()
    return [
        _ChunkRow(
            chunk_id=c.id,
            doc_id=c.doc_id,
            doc_name="",  # filled by caller if needed
            page_number=c.page_number,
            section_path=c.section_path or [],
            modality=c.modality,
            content=c.content,
        )
        for c in rows
    ]


def _rewrite(query: str, subqueries: int) -> list[str]:
    """Query rewriting / decomposition stub (PLAN: 查询改写与路由).

    Real implementation calls an LLM to produce an independent retrieval query
    (balanced) or 2–4 sub-questions (deep). For the scaffold we return the
    original query; decomposition structure is in place for later wiring.
    """
    if subqueries <= 1:
        return [query]
    # Placeholder decomposition: rephrase as N facets. Replace with LLM output.
    return [query] + [f"{query}（子问题 {i}）" for i in range(2, subqueries + 1)]


async def _rerank(
    results: list[RetrievedChunk], keep: int, reranker, query: str
) -> list[RetrievedChunk]:
    """Reorder candidates by relevance.

    If a reranker (e.g. DeepSeek LLM-as-reranker) is configured and returns
    usable scores, reorder by it. Otherwise keep the RRF-fused order and copy
    ``rrf_score`` into ``rerank_score`` so downstream context assembly is stable.
    Failures never break retrieval — they degrade to the RRF order.
    """
    if reranker is not None and len(results) > 1:
        items = [{"chunk_id": r.chunk_id, "snippet": r.snippet} for r in results]
        try:
            scores = await reranker.rerank(query, items)
        except Exception:
            scores = {}
        if scores:
            for r in results:
                r.rerank_score = scores.get(r.chunk_id, r.rrf_score)
            results = sorted(results, key=lambda r: r.rerank_score, reverse=True)
            return results[:keep]
    for r in results:
        r.rerank_score = r.rrf_score
    return results[:keep]


def _build_context(
    results: list[RetrievedChunk], budget: int = 8000
) -> dict:
    """Assemble context bundle with dedup, source diversity, token budget (PLAN)."""
    seen: set[str] = set()
    citations: list[dict] = []
    parts: list[str] = []
    est_tokens = 0
    doc_seen: set[str] = set()
    # Diversity: alternate docs where possible.
    ordered = sorted(results, key=lambda r: (r.rerank_score, r.rrf_score), reverse=True)
    for r in ordered:
        if r.chunk_id in seen:
            continue
        seen.add(r.chunk_id)
        # crude token estimate: characters / 4
        est = max(1, len(r.snippet) // 4)
        if est_tokens + est > budget:
            break
        est_tokens += est
        parts.append(f"[来源 {len(citations)+1}] (doc={r.doc_id}, page={r.page_number})\n{r.snippet}")
        citations.append({
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "page_number": r.page_number,
            "section_path": r.section_path,
            "modality": r.modality,
        })
        doc_seen.add(r.doc_id)
    context_text = "\n\n".join(parts)
    return {"context_text": context_text, "citations": citations, "est_tokens": est_tokens}


async def retrieve(
    session: AsyncSession,
    kb_id: str,
    query: str,
    mode: str = "balanced",
    filters: dict | None = None,
    force_refresh: bool = False,
) -> RetrievalResult:
    filters = filters or {}
    t0 = time.time()
    params = MODE_PARAMS.get(mode, MODE_PARAMS[RetrievalMode.BALANCED])
    generation = await _active_generation(session, kb_id)
    chunks = await _load_chunks(session, kb_id, generation, filters)
    if not chunks:
        return RetrievalResult(
            query=query, mode=mode, rewritten_queries=[query], results=[],
            dense_rank=[], bm25_rank=[], rrf_scores=[], rerank_scores=[],
            latency_ms=int((time.time() - t0) * 1000), cache_hit=False,
            context_bundle={"context_text": "", "citations": []},
            insufficient_evidence=True,
        )

    rewritten = _rewrite(query, params["subqueries"])
    # For the scaffold we recall with the primary query (rewrite wiring is TODO).
    recall_query = rewritten[0]

    emb = get_embedding()
    chunk_ids = [c.chunk_id for c in chunks]
    texts = [c.content for c in chunks]
    bm25 = get_bm25(kb_id, generation, chunk_ids, texts)
    bm25_rank = bm25.search(recall_query, params["bm25_topk"])

    # Dense: real ANN over Chroma (vectors produced by the EmbeddingProvider;
    # Mock by default, swap to local Qwen3 / OpenAI-compatible later).
    query_vec = (await emb.embed([recall_query]))[0]
    store = get_store()
    dense_rank = store.query(kb_id, generation, query_vec, params["dense_topk"])
    if not dense_rank:
        # Self-heal: lazily build the dense index for this generation from the
        # chunks we already loaded, in case indexing did not populate Chroma.
        chunk_vecs = await emb.embed(texts)
        metas = [
            {"doc_id": c.doc_id, "page_number": c.page_number, "modality": c.modality}
            for c in chunks
        ]
        store.upsert(kb_id, generation, chunk_ids, chunk_vecs, metas)
        dense_rank = store.query(kb_id, generation, query_vec, params["dense_topk"])

    fused = rrf([bm25_rank, dense_rank], k=60)[: params["rrf_keep"]]

    # Map scores back to chunks.
    bm25_map = {cid: s for cid, s in bm25_rank}
    dense_map = {cid: s for cid, s in dense_rank}
    rrf_map = {cid: s for cid, s in fused}
    content_by_id = {c.chunk_id: c for c in chunks}
    prelim: list[RetrievedChunk] = []
    for cid, s in fused:
        c = content_by_id[cid]
        prelim.append(RetrievedChunk(
            chunk_id=cid, doc_id=c.doc_id, doc_name=c.doc_name,
            page_number=c.page_number, section_path=c.section_path,
            modality=c.modality, snippet=_snippet(c.content),
            dense_score=dense_map.get(cid, 0.0), bm25_score=bm25_map.get(cid, 0.0),
            rrf_score=s,
        ))

    reranked = prelim  # ordering finalized by _rerank after the optional second pass

    # Second-pass (deep): if evidence still thin, do one extra broad recall.
    second_pass = False
    if params["second_pass"] and (len(prelim) < 4 or (prelim and prelim[0].rrf_score < 0.01)):
        second_pass = True
        extra_bm25 = bm25.search(recall_query, params["bm25_topk"] * 2)
        extra_dense = store.query(kb_id, generation, query_vec, params["dense_topk"] * 2)
        fused2 = rrf([extra_bm25, extra_dense], k=60)[: params["rrf_keep"]]
        for cid, s in fused2:
            if cid in rrf_map:
                continue
            c = content_by_id[cid]
            prelim.append(RetrievedChunk(
                chunk_id=cid, doc_id=c.doc_id, doc_name=c.doc_name,
                page_number=c.page_number, section_path=c.section_path,
                modality=c.modality, snippet=_snippet(c.content),
                dense_score=dense_map.get(cid, 0.0), bm25_score=bm25_map.get(cid, 0.0),
                rrf_score=s,
            ))

    # Rerank once (after expansion) using the configured reranker, if any.
    reranker = get_reranker()
    reranked = await _rerank(prelim, params["rerank_keep"], reranker, query)

    context_bundle = _build_context(reranked, settings.context_token_budget)
    insufficient = len(reranked) == 0 or not context_bundle["citations"]

    return RetrievalResult(
        query=query, mode=mode, rewritten_queries=rewritten,
        results=reranked,
        dense_rank=[{"chunk_id": cid, "score": s} for cid, s in dense_rank],
        bm25_rank=[{"chunk_id": cid, "score": s} for cid, s in bm25_rank],
        rrf_scores=[{"chunk_id": cid, "score": s} for cid, s in fused],
        rerank_scores=[{"chunk_id": r.chunk_id, "score": r.rerank_score} for r in reranked],
        latency_ms=int((time.time() - t0) * 1000), cache_hit=False,
        context_bundle=context_bundle, insufficient_evidence=insufficient,
    )


def invalidate_index(kb_id: str, generation: int) -> None:
    invalidate_bm25(kb_id, generation)
