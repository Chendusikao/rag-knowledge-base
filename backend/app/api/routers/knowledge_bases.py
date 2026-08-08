"""Knowledge base CRUD (PLAN 3 endpoints)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.utils.id import kb_id

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


async def _to_out(session: AsyncSession, kb: KnowledgeBase) -> KnowledgeBaseOut:
    cnt = (
        await session.execute(
            select(func.count(Document.id)).where(Document.kb_id == kb.id)
        )
    ).scalar_one()
    out = KnowledgeBaseOut.model_validate(kb)
    out.document_count = cnt or 0
    return out


@router.post("", response_model=KnowledgeBaseOut)
async def create_kb(
    body: KnowledgeBaseCreate, session: AsyncSession = Depends(_gs)
) -> KnowledgeBaseOut:
    kb = KnowledgeBase(id=kb_id(), **body.model_dump())
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    return await _to_out(session, kb)


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_kbs(session: AsyncSession = Depends(_gs)) -> list[KnowledgeBaseOut]:
    kbs = (
        await session.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    ).scalars().all()
    out = []
    for kb in kbs:
        out.append(await _to_out(session, kb))
    return out


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(kb_id: str, session: AsyncSession = Depends(_gs)) -> KnowledgeBaseOut:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return await _to_out(session, kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseOut)
async def update_kb(
    kb_id: str, body: KnowledgeBaseUpdate, session: AsyncSession = Depends(_gs)
) -> KnowledgeBaseOut:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(kb, field, value)
    await session.commit()
    await session.refresh(kb)
    return await _to_out(session, kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(kb_id: str, session: AsyncSession = Depends(_gs)) -> None:
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    await session.delete(kb)
    await session.commit()
