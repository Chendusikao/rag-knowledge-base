"""Enterprise departments, users, knowledge permissions, audit and security status."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles, utc_now
from app.core.config import settings
from app.db.session import get_session as _gs
from app.models.common import SystemRole
from app.models.enterprise import (
    AuditEvent,
    AuthSession,
    Department,
    EnterpriseUser,
    KnowledgeBasePermission,
    KnowledgeBaseScope,
)
from app.schemas.enterprise import (
    AuditEventList,
    AuditEventOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    PasswordResetRequest,
    PermissionOut,
    PermissionSet,
    SecurityStatusOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.audit import record_audit
from app.services.enterprise import require_kb_access
from app.services.security import hash_password
from app.utils.id import department_id, permission_id, user_id

router = APIRouter(prefix="/api/v1", tags=["enterprise"])
AdminUser = Annotated[EnterpriseUser, Depends(require_roles(SystemRole.ADMIN))]
AuditUser = Annotated[
    EnterpriseUser, Depends(require_roles(SystemRole.ADMIN, SystemRole.AUDITOR))
]
ManagerUser = Annotated[
    EnterpriseUser,
    Depends(require_roles(SystemRole.ADMIN, SystemRole.DEPARTMENT_MANAGER)),
]


async def _department_out(session: AsyncSession, department: Department) -> DepartmentOut:
    user_count = (
        await session.execute(
            select(func.count(EnterpriseUser.id)).where(
                EnterpriseUser.department_id == department.id,
                EnterpriseUser.is_active.is_(True),
            )
        )
    ).scalar_one()
    kb_count = (
        await session.execute(
            select(func.count(KnowledgeBaseScope.id)).where(
                KnowledgeBaseScope.department_id == department.id
            )
        )
    ).scalar_one()
    out = DepartmentOut.model_validate(department)
    out.user_count = user_count
    out.knowledge_base_count = kb_count
    return out


async def _user_out(session: AsyncSession, user: EnterpriseUser) -> UserOut:
    department_name = None
    if user.department_id:
        department = await session.get(Department, user.department_id)
        department_name = department.name if department else None
    out = UserOut.model_validate(user)
    out.department_name = department_name
    return out


async def _require_department(session: AsyncSession, department_value: str | None) -> Department | None:
    if department_value is None:
        return None
    department = await session.get(Department, department_value)
    if department is None or not department.is_active:
        raise HTTPException(status_code=400, detail="部门不存在或已停用")
    return department


def _manager_can_manage_user(actor: EnterpriseUser, target_department_id: str | None, target_role: str) -> None:
    if actor.system_role == SystemRole.ADMIN:
        return
    if target_department_id != actor.department_id:
        raise HTTPException(status_code=403, detail="部门负责人只能管理本部门成员")
    if target_role not in {SystemRole.MEMBER}:
        raise HTTPException(status_code=403, detail="部门负责人只能创建或维护普通成员")


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    session: Annotated[AsyncSession, Depends(_gs)],
    _: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> list[DepartmentOut]:
    departments = (
        await session.execute(select(Department).order_by(Department.name))
    ).scalars().all()
    return [await _department_out(session, department) for department in departments]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    body: DepartmentCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: AdminUser,
) -> DepartmentOut:
    duplicate = (
        await session.execute(
            select(Department.id).where(
                or_(Department.name == body.name.strip(), Department.code == body.code.lower())
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="部门名称或编码已存在")
    department = Department(
        id=department_id(),
        name=body.name.strip(),
        code=body.code.lower(),
        description=body.description.strip(),
    )
    session.add(department)
    await session.flush()
    await record_audit(
        session,
        actor=actor,
        action="department.created",
        resource_type="department",
        resource_id=department.id,
        department_id=department.id,
        details={"code": department.code},
        request=request,
    )
    await session.commit()
    await session.refresh(department)
    return await _department_out(session, department)


@router.put("/departments/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: str,
    body: DepartmentUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: AdminUser,
) -> DepartmentOut:
    department = await session.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="部门不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(department, field, value)
    await record_audit(
        session,
        actor=actor,
        action="department.updated",
        resource_type="department",
        resource_id=department.id,
        department_id=department.id,
        details={"fields": ",".join(body.model_fields_set)},
        request=request,
    )
    await session.commit()
    await session.refresh(department)
    return await _department_out(session, department)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: Annotated[
        EnterpriseUser,
        Depends(require_roles(SystemRole.ADMIN, SystemRole.AUDITOR, SystemRole.DEPARTMENT_MANAGER)),
    ],
) -> list[UserOut]:
    query = select(EnterpriseUser).order_by(EnterpriseUser.display_name)
    if actor.system_role == SystemRole.DEPARTMENT_MANAGER:
        query = query.where(EnterpriseUser.department_id == actor.department_id)
    users = (await session.execute(query)).scalars().all()
    return [await _user_out(session, user) for user in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: ManagerUser,
) -> UserOut:
    await _require_department(session, body.department_id)
    _manager_can_manage_user(actor, body.department_id, body.system_role)
    email = str(body.email).lower()
    duplicate = (
        await session.execute(select(EnterpriseUser.id).where(EnterpriseUser.email == email))
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="该邮箱已存在")
    user = EnterpriseUser(
        id=user_id(),
        email=email,
        display_name=body.display_name.strip(),
        department_id=body.department_id,
        system_role=body.system_role,
        password_hash=await asyncio.to_thread(hash_password, body.temporary_password),
        must_change_password=True,
    )
    session.add(user)
    await session.flush()
    await record_audit(
        session,
        actor=actor,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        department_id=user.department_id,
        details={"role": user.system_role},
        request=request,
    )
    await session.commit()
    await session.refresh(user)
    return await _user_out(session, user)


@router.put("/users/{target_user_id}", response_model=UserOut)
async def update_user(
    target_user_id: str,
    body: UserUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: ManagerUser,
) -> UserOut:
    target = await session.get(EnterpriseUser, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    values = body.model_dump(exclude_unset=True)
    next_department = values.get("department_id", target.department_id)
    next_role = values.get("system_role", target.system_role)
    await _require_department(session, next_department)
    _manager_can_manage_user(actor, next_department, next_role)
    if actor.id == target.id and values.get("is_active") is False:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    if target.system_role == SystemRole.ADMIN and (
        values.get("is_active") is False or next_role != SystemRole.ADMIN
    ):
        active_admins = (
            await session.execute(
                select(func.count(EnterpriseUser.id)).where(
                    EnterpriseUser.system_role == SystemRole.ADMIN,
                    EnterpriseUser.is_active.is_(True),
                )
            )
        ).scalar_one()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="系统必须保留至少一名有效管理员")
    for field, value in values.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(target, field, value)
    if values.get("is_active") is False:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
    await record_audit(
        session,
        actor=actor,
        action="user.updated",
        resource_type="user",
        resource_id=target.id,
        department_id=target.department_id,
        details={"fields": ",".join(values)},
        request=request,
    )
    await session.commit()
    await session.refresh(target)
    return await _user_out(session, target)


@router.post("/users/{target_user_id}/reset-password", status_code=204)
async def reset_password(
    target_user_id: str,
    body: PasswordResetRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: ManagerUser,
) -> None:
    target = await session.get(EnterpriseUser, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    _manager_can_manage_user(actor, target.department_id, target.system_role)
    target.password_hash = await asyncio.to_thread(hash_password, body.temporary_password)
    target.must_change_password = True
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    await record_audit(
        session,
        actor=actor,
        action="user.password_reset",
        resource_type="user",
        resource_id=target.id,
        department_id=target.department_id,
        request=request,
    )
    await session.commit()


@router.get("/knowledge-bases/{kb_id}/permissions", response_model=list[PermissionOut])
async def list_kb_permissions(
    kb_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> list[PermissionOut]:
    await require_kb_access(session, actor, kb_id, "manager", request=request)
    rows = (
        await session.execute(
            select(KnowledgeBasePermission, EnterpriseUser)
            .join(EnterpriseUser, EnterpriseUser.id == KnowledgeBasePermission.user_id)
            .where(KnowledgeBasePermission.kb_id == kb_id)
            .order_by(EnterpriseUser.display_name)
        )
    ).all()
    return [
        PermissionOut(
            id=permission.id,
            kb_id=permission.kb_id,
            user_id=user.id,
            user_email=user.email,
            user_display_name=user.display_name,
            access_level=permission.access_level,
            granted_by=permission.granted_by,
            created_at=permission.created_at,
            updated_at=permission.updated_at,
        )
        for permission, user in rows
    ]


@router.put("/knowledge-bases/{kb_id}/permissions", response_model=PermissionOut)
async def set_kb_permission(
    kb_id: str,
    body: PermissionSet,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> PermissionOut:
    await require_kb_access(session, actor, kb_id, "manager", request=request)
    user = await session.get(EnterpriseUser, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="授权用户不存在或已停用")
    permission = (
        await session.execute(
            select(KnowledgeBasePermission).where(
                KnowledgeBasePermission.kb_id == kb_id,
                KnowledgeBasePermission.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if permission is None:
        permission = KnowledgeBasePermission(
            id=permission_id(),
            kb_id=kb_id,
            user_id=user.id,
            access_level=body.access_level,
            granted_by=actor.id,
        )
        session.add(permission)
    else:
        permission.access_level = body.access_level
        permission.granted_by = actor.id
    await session.flush()
    await record_audit(
        session,
        actor=actor,
        action="permission.granted",
        resource_type="knowledge_base",
        resource_id=kb_id,
        department_id=user.department_id,
        details={"target_user_id": user.id, "access_level": body.access_level},
        request=request,
    )
    await session.commit()
    await session.refresh(permission)
    return PermissionOut(
        id=permission.id,
        kb_id=kb_id,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.display_name,
        access_level=permission.access_level,
        granted_by=permission.granted_by,
        created_at=permission.created_at,
        updated_at=permission.updated_at,
    )


@router.delete("/knowledge-bases/{kb_id}/permissions/{target_user_id}", status_code=204)
async def revoke_kb_permission(
    kb_id: str,
    target_user_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    actor: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> None:
    await require_kb_access(session, actor, kb_id, "manager", request=request)
    permission = (
        await session.execute(
            select(KnowledgeBasePermission).where(
                KnowledgeBasePermission.kb_id == kb_id,
                KnowledgeBasePermission.user_id == target_user_id,
            )
        )
    ).scalar_one_or_none()
    if permission is None:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    await session.delete(permission)
    await record_audit(
        session,
        actor=actor,
        action="permission.revoked",
        resource_type="knowledge_base",
        resource_id=kb_id,
        details={"target_user_id": target_user_id},
        request=request,
    )
    await session.commit()


@router.get("/audit-events", response_model=AuditEventList)
async def list_audit_events(
    session: Annotated[AsyncSession, Depends(_gs)],
    _: AuditUser,
    action: str | None = None,
    outcome: str | None = None,
    actor_user_id: str | None = None,
    department_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditEventList:
    filters = []
    if action:
        filters.append(AuditEvent.action == action)
    if outcome:
        filters.append(AuditEvent.outcome == outcome)
    if actor_user_id:
        filters.append(AuditEvent.actor_user_id == actor_user_id)
    if department_id:
        filters.append(AuditEvent.department_id == department_id)
    if start_at:
        filters.append(AuditEvent.created_at >= start_at)
    if end_at:
        filters.append(AuditEvent.created_at <= end_at)
    total = (
        await session.execute(select(func.count(AuditEvent.id)).where(*filters))
    ).scalar_one()
    events = (
        await session.execute(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return AuditEventList(
        items=[AuditEventOut.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/security/status", response_model=SecurityStatusOut)
async def security_status(_: AuditUser) -> SecurityStatusOut:
    return SecurityStatusOut(
        authentication="已启用密码登录与服务端会话",
        password_storage=f"PBKDF2-SHA256（{settings.password_pbkdf2_iterations:,} 次迭代）",
        session_cookie="HttpOnly + SameSite=Lax" + (" + Secure" if settings.auth_cookie_secure else "（本地 HTTP 未启用 Secure）"),
        csrf_protection="来源白名单 + 自定义请求标记",
        audit_log="数据库触发器保护的只追加日志",
        storage_encryption=(
            "部署环境已声明启用磁盘加密"
            if settings.storage_encryption_configured
            else "未配置；生产环境应启用 BitLocker 或等效磁盘加密"
        ),
        storage_encryption_configured=settings.storage_encryption_configured,
    )
