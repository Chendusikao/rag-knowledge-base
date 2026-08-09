"""Department defaults and knowledge-base access resolution."""
from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import KnowledgeAccessLevel, KnowledgeAccessScope, SystemRole
from app.models.enterprise import (
    DEFAULT_DEPARTMENT_ID,
    Department,
    EnterpriseUser,
    KnowledgeBasePermission,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.services.audit import record_audit
from app.utils.id import new_id


_ACCESS_RANK = {
    KnowledgeAccessLevel.VIEWER: 1,
    KnowledgeAccessLevel.EDITOR: 2,
    KnowledgeAccessLevel.MANAGER: 3,
}


async def prepare_enterprise_state(session: AsyncSession) -> None:
    department = await session.get(Department, DEFAULT_DEPARTMENT_ID)
    if department is None:
        department = Department(
            id=DEFAULT_DEPARTMENT_ID,
            name="公司公共",
            code="company",
            description="企业默认部门，用于承接升级前已有的知识库。",
        )
        session.add(department)
        await session.flush()

    existing_scope_ids = set(
        (await session.execute(select(KnowledgeBaseScope.kb_id))).scalars().all()
    )
    knowledge_bases = (await session.execute(select(KnowledgeBase.id))).scalars().all()
    for kb_id in knowledge_bases:
        if kb_id not in existing_scope_ids:
            session.add(
                KnowledgeBaseScope(
                    id=new_id("scope"),
                    kb_id=kb_id,
                    department_id=DEFAULT_DEPARTMENT_ID,
                    access_scope=KnowledgeAccessScope.DEPARTMENT,
                )
            )
    await session.commit()


async def get_or_create_scope(
    session: AsyncSession,
    kb_id: str,
    *,
    department_id: str = DEFAULT_DEPARTMENT_ID,
    access_scope: str = KnowledgeAccessScope.DEPARTMENT,
) -> KnowledgeBaseScope:
    scope = (
        await session.execute(
            select(KnowledgeBaseScope).where(KnowledgeBaseScope.kb_id == kb_id)
        )
    ).scalar_one_or_none()
    if scope is None:
        scope = KnowledgeBaseScope(
            id=new_id("scope"),
            kb_id=kb_id,
            department_id=department_id,
            access_scope=access_scope,
        )
        session.add(scope)
        await session.flush()
    return scope


async def resolve_kb_access(
    session: AsyncSession, user: EnterpriseUser, kb_id: str
) -> str | None:
    if user.system_role == SystemRole.ADMIN:
        return KnowledgeAccessLevel.MANAGER

    scope = (
        await session.execute(
            select(KnowledgeBaseScope).where(KnowledgeBaseScope.kb_id == kb_id)
        )
    ).scalar_one_or_none()
    if scope is None:
        scope = await get_or_create_scope(session, kb_id)

    same_department = bool(user.department_id and user.department_id == scope.department_id)
    if user.system_role == SystemRole.DEPARTMENT_MANAGER and same_department:
        return KnowledgeAccessLevel.MANAGER

    explicit = (
        await session.execute(
            select(KnowledgeBasePermission).where(
                KnowledgeBasePermission.kb_id == kb_id,
                KnowledgeBasePermission.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if explicit is not None:
        return explicit.access_level
    if (
        user.system_role == SystemRole.MEMBER
        and same_department
        and scope.access_scope == KnowledgeAccessScope.DEPARTMENT
    ):
        return KnowledgeAccessLevel.VIEWER
    return None


async def require_kb_access(
    session: AsyncSession,
    user: EnterpriseUser,
    kb_id: str,
    required: str,
    *,
    request: Request | None = None,
) -> str:
    actual = await resolve_kb_access(session, user, kb_id)
    if actual is None or _ACCESS_RANK.get(actual, 0) < _ACCESS_RANK[required]:
        await record_audit(
            session,
            actor=user,
            action="permission.denied",
            resource_type="knowledge_base",
            resource_id=kb_id,
            outcome="denied",
            details={"required_access": required, "actual_access": actual or "none"},
            request=request,
        )
        await session.commit()
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return actual
