"""Document endpoints: upload, reindex, delete, open original file (PLAN 3)."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.models.chunk import Chunk
from app.models.common import DocStatus, JobType
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document import DocumentOut, DocumentUploadResponse
from app.services.retrieval.manager import invalidate_index
from app.services.storage import save_upload
from app.services.task_system import enqueue_job
from app.utils.hash import sha256_file

router = APIRouter(prefix="/api/v1", tags=["documents"])


async def _kb_or_404(session: AsyncSession, kb_id: str) -> KnowledgeBase:
    kb = (await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return kb


@router.post("/knowledge-bases/{kb_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    kb_id: str, file: UploadFile = File(...), session: AsyncSession = Depends(_gs)
) -> DocumentUploadResponse:
    await _kb_or_404(session, kb_id)
    try:
        meta = await save_upload(kb_id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    content_hash = sha256_file(meta["storage_path"])
    doc = Document(
        id=meta["doc_id"], kb_id=kb_id, filename=meta["filename"],
        mime_type=meta["mime_type"], ext=meta["ext"], content_hash=content_hash,
        size_bytes=meta["size_bytes"], status=DocStatus.PENDING,
        storage_path=meta["storage_path"],
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    # Queue an indexing job (handled by the worker; runs in-process for dev).
    job = await enqueue_job(
        session, JobType.INDEX, kb_id, doc_id=doc.id,
        payload={"storage_path": meta["storage_path"], "ext": meta["ext"]},
    )
    return DocumentUploadResponse(document=DocumentOut.model_validate(doc), job_id=job.id)


@router.post("/documents/{doc_id}/reindex", response_model=DocumentOut)
async def reindex_document(doc_id: str, session: AsyncSession = Depends(_gs)) -> DocumentOut:
    doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    doc.status = DocStatus.INDEXING
    await session.commit()
    await session.refresh(doc)
    await enqueue_job(
        session, JobType.REINDEX, doc.kb_id, doc_id=doc.id,
        payload={"storage_path": doc.storage_path, "ext": doc.ext},
    )
    return DocumentOut.model_validate(doc)


@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str, session: AsyncSession = Depends(_gs)) -> FileResponse:
    """返回文档的原始文件（供网页「参考来源」点击直接打开/下载）。

    仅读取数据库中该文档记录的存储路径，不接收任意路径参数。
    """
    doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if doc is None or not doc.storage_path:
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(doc.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found on disk")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=doc.filename or path.name,
        content_disposition_type="inline",
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, session: AsyncSession = Depends(_gs)) -> None:
    doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    # PLAN: 删除文档时同步清理 Chroma、BM25 和相关缓存；聊天历史引用保留为快照。
    await session.execute(delete(Chunk).where(Chunk.doc_id == doc_id))
    invalidate_index(doc.kb_id, 0)  # process-local BM25 cache cleared on next load
    await session.delete(doc)
    await session.commit()
