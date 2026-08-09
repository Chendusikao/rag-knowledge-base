"""Knowledge base CRUD (PLAN 3 endpoints)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session as _gs
from app.models.common import KnowledgeAccessLevel, SystemRole
from app.models.document import Document
from app.models.enterprise import Department, EnterpriseUser, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.utils.id import kb_id
from app.services.audit import record_audit
from app.services.enterprise import get_or_create_scope, require_kb_access, resolve_kb_access
from app.services.storage import delete_knowledge_base_storage

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


async def _to_out(
    session: AsyncSession, kb: KnowledgeBase, user: EnterpriseUser
) -> KnowledgeBaseOut:
    cnt = (
        await session.execute(
            select(func.count(Document.id)).where(Document.kb_id == kb.id)
        )
    ).scalar_one()
    out = KnowledgeBaseOut.model_validate(kb)
    out.document_count = cnt or 0
    scope = await get_or_create_scope(session, kb.id)
    department = await session.get(Department, scope.department_id)
    out.department_id = scope.department_id
    out.department_name = department.name if department else "未知部门"
    out.access_scope = scope.access_scope
    out.access_level = await resolve_kb_access(session, user, kb.id) or "none"
    return out


@router.post("", response_model=KnowledgeBaseOut)
async def create_kb(
    body: KnowledgeBaseCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> KnowledgeBaseOut:
    if user.system_role not in {SystemRole.ADMIN, SystemRole.DEPARTMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="只有管理员或部门负责人可以创建知识库")
    department_id = body.department_id or user.department_id
    if not department_id:
        raise HTTPException(status_code=400, detail="必须选择所属部门")
    department = await session.get(Department, department_id)
    if department is None or not department.is_active:
        raise HTTPException(status_code=400, detail="所属部门不存在或已停用")
    if user.system_role == SystemRole.DEPARTMENT_MANAGER and department_id != user.department_id:
        raise HTTPException(status_code=403, detail="部门负责人只能在本部门创建知识库")
    data = body.model_dump()
    access_scope = data.pop("access_scope")
    data.pop("department_id")
    kb = KnowledgeBase(id=kb_id(), **data)
    session.add(kb)
    await session.flush()
    await get_or_create_scope(
        session, kb.id, department_id=department_id, access_scope=access_scope
    )
    await record_audit(
        session,
        actor=user,
        action="knowledge_base.created",
        resource_type="knowledge_base",
        resource_id=kb.id,
        department_id=department_id,
        details={"access_scope": access_scope},
        request=request,
    )
    await session.commit()
    await session.refresh(kb)
    return await _to_out(session, kb, user)


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_kbs(
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> list[KnowledgeBaseOut]:
    kbs = (
        await session.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    ).scalars().all()
    out = []
    for kb in kbs:
        if await resolve_kb_access(session, user, kb.id):
            out.append(await _to_out(session, kb, user))
    return out


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(
    kb_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> KnowledgeBaseOut:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    await require_kb_access(session, user, kb_id, KnowledgeAccessLevel.VIEWER, request=request)
    return await _to_out(session, kb, user)


@router.put("/{kb_id}", response_model=KnowledgeBaseOut)
async def update_kb(
    kb_id: str,
    body: KnowledgeBaseUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> KnowledgeBaseOut:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    values = body.model_dump(exclude_unset=True)
    changes_scope = "department_id" in values or "access_scope" in values
    required = KnowledgeAccessLevel.MANAGER if changes_scope else KnowledgeAccessLevel.EDITOR
    await require_kb_access(session, user, kb_id, required, request=request)
    department_id = values.pop("department_id", None)
    access_scope = values.pop("access_scope", None)
    scope = await get_or_create_scope(session, kb_id)
    if department_id is not None:
        department = await session.get(Department, department_id)
        if department is None or not department.is_active:
            raise HTTPException(status_code=400, detail="所属部门不存在或已停用")
        if user.system_role == SystemRole.DEPARTMENT_MANAGER and department_id != user.department_id:
            raise HTTPException(status_code=403, detail="部门负责人不能转移到其他部门")
        scope.department_id = department_id
    if access_scope is not None:
        scope.access_scope = access_scope
    for field, value in values.items():
        setattr(kb, field, value)
    await record_audit(
        session,
        actor=user,
        action="knowledge_base.updated",
        resource_type="knowledge_base",
        resource_id=kb.id,
        department_id=scope.department_id,
        details={"fields": ",".join(body.model_fields_set)},
        request=request,
    )
    await session.commit()
    await session.refresh(kb)
    return await _to_out(session, kb, user)


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(
    kb_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> None:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    await require_kb_access(
        session, user, kb_id, KnowledgeAccessLevel.MANAGER, request=request
    )
    scope = (
        await session.execute(
            select(KnowledgeBaseScope).where(KnowledgeBaseScope.kb_id == kb_id)
        )
    ).scalar_one_or_none()
    await record_audit(
        session,
        actor=user,
        action="knowledge_base.deleted",
        resource_type="knowledge_base",
        resource_id=kb.id,
        department_id=scope.department_id if scope else None,
        details={"document_count": (await _to_out(session, kb, user)).document_count},
        request=request,
    )
    await session.delete(kb)
    await session.commit()
    try:
        delete_knowledge_base_storage(kb_id)
    except OSError:
        pass
