"""Admin-only scanning and governed import from the enterprise source library."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.config import settings
from app.db.session import get_session as _gs
from app.models.common import DocStatus, JobType, SystemRole
from app.models.document import Document
from app.models.enterprise import Department, EnterpriseUser
from app.models.knowledge_base import KnowledgeBase
from app.schemas.enterprise import (
    SourceBranchImportOut,
    SourceBranchImportRequest,
    SourceBranchOut,
    SourceLibraryOut,
)
from app.services.audit import record_audit
from app.services.enterprise import get_or_create_scope
from app.services.source_library import (
    SourceLibraryError,
    available_source_root,
    scan_branch,
    scan_source_library,
)
from app.services.storage import copy_source_file, delete_document_storage
from app.services.task_system import enqueue_job
from app.utils.hash import sha256_file
from app.utils.id import kb_id


router = APIRouter(prefix="/api/v1/source-library", tags=["source-library"])
AdminUser = Annotated[EnterpriseUser, Depends(require_roles(SystemRole.ADMIN))]


def _branch_out(snapshot) -> SourceBranchOut:
    return SourceBranchOut(
        name=snapshot.name,
        total_file_count=snapshot.total_file_count,
        supported_file_count=snapshot.supported_file_count,
        importable_file_count=snapshot.importable_file_count,
        unsupported_file_count=snapshot.unsupported_file_count,
        oversized_file_count=snapshot.oversized_file_count,
        total_size_bytes=snapshot.total_size_bytes,
        extension_counts=snapshot.extension_counts,
        last_modified_at=snapshot.last_modified_at,
        sensitive=snapshot.sensitive,
        recommended_access_scope=snapshot.recommended_access_scope,
        truncated=snapshot.truncated,
    )


@router.get("/branches", response_model=SourceLibraryOut)
async def list_source_branches(_: AdminUser) -> SourceLibraryOut:
    root, available, branches = await asyncio.to_thread(scan_source_library)
    return SourceLibraryOut(
        root=str(root),
        available=available,
        branches=[_branch_out(branch) for branch in branches],
    )


@router.post("/imports", response_model=SourceBranchImportOut)
async def import_source_branch(
    body: SourceBranchImportRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: AdminUser,
) -> SourceBranchImportOut:
    department = await session.get(Department, body.department_id)
    if department is None or not department.is_active:
        raise HTTPException(status_code=400, detail="所属部门不存在或已停用")

    root = available_source_root()
    if root is None:
        raise HTTPException(status_code=503, detail="总资料库目录不存在或不可读取")
    try:
        snapshot = await asyncio.to_thread(scan_branch, root, body.branch_name)
    except SourceLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if snapshot.truncated:
        raise HTTPException(status_code=409, detail="该分支文件过多，扫描结果不完整，已停止导入")
    if snapshot.importable_file_count == 0:
        raise HTTPException(status_code=400, detail="该分支没有可导入的受支持文件")
    if snapshot.importable_file_count > settings.knowledge_source_import_limit:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多导入 {settings.knowledge_source_import_limit} 个文件",
        )
    if (
        snapshot.sensitive
        and body.access_scope == "department"
        and not body.confirm_sensitive_department_access
    ):
        raise HTTPException(
            status_code=400,
            detail="敏感分支默认必须受限；若要部门共享，需要再次明确确认",
        )

    all_kbs = (await session.execute(select(KnowledgeBase))).scalars().all()
    mapped = [
        item
        for item in all_kbs
        if isinstance(item.settings, dict)
        and item.settings.get("source_library_branch") == snapshot.name
    ]
    if len(mapped) > 1:
        raise HTTPException(status_code=409, detail="该分支关联了多个知识库，请先整理关联关系")
    same_name = [item for item in all_kbs if item.name == snapshot.name]
    if not mapped and len(same_name) > 1:
        raise HTTPException(status_code=409, detail="存在多个同名知识库，无法确定同步目标")

    created_kb = False
    kb = mapped[0] if mapped else (same_name[0] if same_name else None)
    if kb is None:
        kb = KnowledgeBase(
            id=kb_id(),
            name=snapshot.name,
            description=f"从总资料库分支“{snapshot.name}”受管导入；源目录保持只读。",
            embedding_model="Qwen3-Embedding-0.6B",
            reranker_model="Qwen3-Reranker-0.6B",
            vision_enabled=False,
            settings={},
        )
        session.add(kb)
        await session.flush()
        created_kb = True

    kb_settings = dict(kb.settings or {})
    kb_settings.update(
        {
            "source_library_branch": snapshot.name,
            "source_copy_mode": "managed_copy",
            "source_last_sync_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    kb.settings = kb_settings
    scope = await get_or_create_scope(
        session,
        kb.id,
        department_id=department.id,
        access_scope=body.access_scope,
    )
    scope.department_id = department.id
    scope.access_scope = body.access_scope

    existing_hashes = set(
        (await session.execute(select(Document.content_hash).where(Document.kb_id == kb.id)))
        .scalars()
        .all()
    )
    imported = skipped = failed = 0
    job_ids: list[str] = []
    for source in snapshot.files:
        try:
            content_hash = await asyncio.to_thread(sha256_file, str(source.path))
            if content_hash in existing_hashes:
                skipped += 1
                continue
            meta = await asyncio.to_thread(
                copy_source_file,
                kb.id,
                source.path,
                source.display_name,
            )
            stored_hash = await asyncio.to_thread(sha256_file, meta["storage_path"])
            if stored_hash in existing_hashes:
                await asyncio.to_thread(delete_document_storage, meta["storage_path"])
                skipped += 1
                continue
            content_hash = stored_hash
        except (OSError, ValueError):
            failed += 1
            continue

        doc = Document(
            id=meta["doc_id"],
            kb_id=kb.id,
            filename=meta["filename"],
            mime_type=meta["mime_type"],
            ext=meta["ext"],
            content_hash=content_hash,
            size_bytes=meta["size_bytes"],
            status=DocStatus.PENDING,
            storage_path=meta["storage_path"],
        )
        session.add(doc)
        await session.flush()
        job = await enqueue_job(
            session,
            JobType.INDEX,
            kb.id,
            doc_id=doc.id,
            payload={"storage_path": meta["storage_path"], "ext": meta["ext"]},
            commit=False,
        )
        await record_audit(
            session,
            actor=actor,
            action="document.source_imported",
            resource_type="document",
            resource_id=doc.id,
            department_id=department.id,
            details={
                "source_branch": snapshot.name,
                "extension": doc.ext,
                "size_bytes": doc.size_bytes,
            },
            request=request,
        )
        existing_hashes.add(content_hash)
        imported += 1
        job_ids.append(job.id)

    await record_audit(
        session,
        actor=actor,
        action="source_branch.imported",
        resource_type="knowledge_base",
        resource_id=kb.id,
        department_id=department.id,
        details={
            "source_branch": snapshot.name,
            "access_scope": body.access_scope,
            "created_knowledge_base": created_kb,
            "imported_count": imported,
            "skipped_duplicate_count": skipped,
            "unsupported_count": snapshot.unsupported_file_count,
            "oversized_count": snapshot.oversized_file_count,
            "failed_count": failed,
        },
        request=request,
    )
    await session.commit()

    return SourceBranchImportOut(
        branch_name=snapshot.name,
        knowledge_base_id=kb.id,
        knowledge_base_name=kb.name,
        created_knowledge_base=created_kb,
        imported_count=imported,
        skipped_duplicate_count=skipped,
        unsupported_count=snapshot.unsupported_file_count,
        oversized_count=snapshot.oversized_file_count,
        failed_count=failed,
        job_ids=job_ids,
    )
