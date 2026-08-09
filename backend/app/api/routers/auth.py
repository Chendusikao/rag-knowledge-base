"""First-run bootstrap and cookie-based enterprise authentication."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user, utc_now
from app.core.config import settings
from app.db.session import get_session as _gs
from app.models.common import SystemRole
from app.models.enterprise import (
    DEFAULT_DEPARTMENT_ID,
    AuthSession,
    Department,
    EnterpriseUser,
)
from app.schemas.enterprise import (
    AuthStatusOut,
    BootstrapRequest,
    ChangePasswordRequest,
    LoginRequest,
    UserOut,
)
from app.services.audit import record_audit
from app.services.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.utils.id import auth_session_id, user_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_dummy_password_hash = hash_password("this-is-a-dummy-password-value")


async def _to_user_out(session: AsyncSession, user: EnterpriseUser) -> UserOut:
    department_name = None
    if user.department_id:
        department = await session.get(Department, user.department_id)
        department_name = department.name if department else None
    out = UserOut.model_validate(user)
    out.department_name = department_name
    return out


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    now = time.monotonic()
    attempts = _login_attempts[_client_key(request)]
    while attempts and now - attempts[0] > 300:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请五分钟后重试")
    attempts.append(now)


def _clear_rate_limit(request: Request) -> None:
    _login_attempts.pop(_client_key(request), None)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


async def _new_session(
    session: AsyncSession, user: EnterpriseUser, request: Request
) -> str:
    token = new_session_token()
    session.add(
        AuthSession(
            id=auth_session_id(),
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=utc_now() + timedelta(hours=settings.auth_session_hours),
            ip_address=request.client.host[:64] if request.client else "",
            user_agent=request.headers.get("user-agent", "")[:512],
        )
    )
    return token


@router.get("/status", response_model=AuthStatusOut)
async def auth_status(
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser | None, Depends(get_optional_user)],
) -> AuthStatusOut:
    user_count = (await session.execute(select(func.count(EnterpriseUser.id)))).scalar_one()
    return AuthStatusOut(
        setup_required=user_count == 0,
        authenticated=user is not None,
        user=await _to_user_out(session, user) if user else None,
    )


@router.post("/bootstrap", response_model=UserOut, status_code=201)
async def bootstrap(
    body: BootstrapRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(_gs)],
) -> UserOut:
    if settings.bootstrap_local_only and request.client and request.client.host not in {
        "127.0.0.1", "::1", "localhost", "test", "testclient"
    }:
        raise HTTPException(status_code=403, detail="首次管理员只能在服务器本机创建")
    user_count = (await session.execute(select(func.count(EnterpriseUser.id)))).scalar_one()
    if user_count:
        raise HTTPException(status_code=409, detail="系统已完成初始化")

    department = await session.get(Department, DEFAULT_DEPARTMENT_ID)
    if department is None:
        department = Department(
            id=DEFAULT_DEPARTMENT_ID,
            name=body.organization_name.strip(),
            code="company",
            description="企业默认部门",
        )
        session.add(department)
    else:
        department.name = body.organization_name.strip()

    user = EnterpriseUser(
        id=user_id(),
        email=str(body.email).lower(),
        display_name=body.display_name.strip(),
        department_id=department.id,
        system_role=SystemRole.ADMIN,
        password_hash=await asyncio.to_thread(hash_password, body.password),
    )
    session.add(user)
    await session.flush()
    token = await _new_session(session, user, request)
    await record_audit(
        session,
        actor=user,
        action="auth.bootstrap",
        resource_type="user",
        resource_id=user.id,
        department_id=department.id,
        request=request,
    )
    await session.commit()
    _set_session_cookie(response, token)
    return await _to_user_out(session, user)


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(_gs)],
) -> UserOut:
    _check_rate_limit(request)
    email = str(body.email).lower()
    user = (
        await session.execute(select(EnterpriseUser).where(EnterpriseUser.email == email))
    ).scalar_one_or_none()
    encoded = user.password_hash if user else _dummy_password_hash
    valid_password = await asyncio.to_thread(verify_password, body.password, encoded)
    if user is None or not valid_password or not user.is_active:
        await record_audit(
            session,
            actor=user,
            action="auth.login",
            resource_type="session",
            resource_id="",
            outcome="failed",
            details={"email": email},
            request=request,
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")

    user.last_login_at = utc_now()
    token = await _new_session(session, user, request)
    await record_audit(
        session,
        actor=user,
        action="auth.login",
        resource_type="session",
        resource_id=user.id,
        department_id=user.department_id,
        request=request,
    )
    await session.commit()
    _clear_rate_limit(request)
    _set_session_cookie(response, token)
    await session.refresh(user)
    return await _to_user_out(session, user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser | None, Depends(get_optional_user)],
) -> None:
    auth_session = getattr(request.state, "auth_session", None)
    if auth_session is not None:
        auth_session.revoked_at = utc_now()
    if user:
        await record_audit(
            session,
            actor=user,
            action="auth.logout",
            resource_type="session",
            resource_id=auth_session.id if auth_session else "",
            department_id=user.department_id,
            request=request,
        )
    await session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> UserOut:
    return await _to_user_out(session, user)


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> None:
    valid = await asyncio.to_thread(verify_password, body.current_password, user.password_hash)
    if not valid:
        raise HTTPException(status_code=400, detail="当前密码不正确")
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.must_change_password = False
    current_session = getattr(request.state, "auth_session", None)
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.id != current_session.id)
        .values(revoked_at=utc_now())
    )
    await record_audit(
        session,
        actor=user,
        action="auth.password_changed",
        resource_type="user",
        resource_id=user.id,
        department_id=user.department_id,
        request=request,
    )
    await session.commit()
