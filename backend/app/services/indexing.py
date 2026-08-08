"""Indexing job handler (PLAN 2.Offline — structured chunk + atomic index switch).

Parses **all** documents of the KB, writes Chunks for a *new* KB-wide
generation, embeds them into the persistent Chroma dense store, then atomically
flips the KB's active generation. The previous generation's chunks (and its
Chroma collection) remain until the switch commits, so a failed reindex leaves
the old index fully intact (PLAN: "失败时旧索引继续可用").

Note on generation semantics: the scaffold uses a single KB-wide generation
counter. Every (re)index regenerates the whole KB's chunk set into a new
generation, which keeps the retrieval filter (``generation == active``) correct
across multiple documents — a single-document-only bump would silently drop
other documents from retrieval.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.common import DocStatus
from app.models.document import Document, DocumentVersion
from app.models.knowledge_base import IndexGeneration, KnowledgeBase
from app.models.job import JobRun
from app.services.parsing import parse_document, parser_version_for
from app.services.providers.factory import get_embedding
from app.services.retrieval.dense_store import get_store
from app.utils.hash import sha256_text
from app.utils.id import chunk_id

async def index_document_job(job: JobRun, session: AsyncSession) -> None:
    doc = (
        await session.execute(select(Document).where(Document.id == job.doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise ValueError(f"document {job.doc_id} missing")

    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise ValueError(f"kb {doc.kb_id} missing")

    new_gen = kb.current_generation + 1
    prev_gen = kb.current_generation

    # All documents of this KB that have stored content are (re)indexed so the
    # new generation is a complete, consistent snapshot.
    docs = (
        await session.execute(
            select(Document).where(Document.kb_id == kb.id, Document.storage_path != "")
        )
    ).scalars().all()

    # (id, content, doc_id, page_number, modality)
    new_chunks: list[tuple[str, str, str, int, str]] = []
    for d in docs:
        specs = parse_document(d.storage_path, d.ext)
        version = DocumentVersion(
            doc_id=d.id, version=new_gen, content_hash=d.content_hash,
            parser_version=parser_version_for(d.ext), size_bytes=d.size_bytes, num_pages=d.num_pages,
        )
        session.add(version)
        await session.flush()

        for idx, spec in enumerate(specs):
            cid = chunk_id()
            new_chunks.append((cid, spec.content, d.id, spec.page_number, spec.modality))
            session.add(Chunk(
                id=cid, kb_id=kb.id, doc_id=d.id, version_id=version.id,
                chunk_index=idx, section_path=spec.section_path,
                page_number=spec.page_number, modality=spec.modality,
                content=spec.content, content_hash=sha256_text(spec.content),
                parser_version=parser_version_for(d.ext), token_estimate=max(1, len(spec.content) // 4),
                generation=new_gen,
            ))
        d.status = DocStatus.READY
        d.current_version = new_gen

    # Atomic switch: bump generation + record active generation, then drop older
    # generations. The new chunks (generation == new_gen) are preserved.
    kb.current_generation = new_gen
    session.add(IndexGeneration(
        kb_id=kb.id, generation=new_gen, status="active",
        dense_ready=True, bm25_ready=True, chunk_count=len(new_chunks),
        finished_at=datetime.now(timezone.utc),
    ))
    await session.execute(
        delete(Chunk).where(Chunk.kb_id == kb.id, Chunk.generation < new_gen)
    )
    await session.commit()

    # Persist dense vectors into Chroma for the new generation.
    store = get_store()
    if new_chunks:
        emb = get_embedding()
        ids = [c[0] for c in new_chunks]
        texts = [c[1] for c in new_chunks]
        vectors = await emb.embed(texts)
        metas = [
            {"doc_id": c[2], "page_number": c[3], "modality": c[4]}
            for c in new_chunks
        ]
        store.upsert(kb.id, new_gen, ids, vectors, metas)

    # Reclaim space: drop the previous generation's Chroma collection.
    if prev_gen > 0:
        try:
            store.delete_collection(kb.id, prev_gen)
        except Exception:  # noqa: BLE001
            pass
