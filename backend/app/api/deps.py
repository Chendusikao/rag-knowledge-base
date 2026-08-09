"""Shared API dependencies for sessions, authentication and system roles."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.enterprise import AuthSession, EnterpriseUser
from app.services.security import hash_session_token


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def get_optional_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EnterpriseUser | None:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    token_hash = hash_session_token(token)
    row = (
        await session.execute(
            select(AuthSession, EnterpriseUser)
            .join(EnterpriseUser, EnterpriseUser.id == AuthSession.user_id)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > utc_now(),
                EnterpriseUser.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    auth_session, user = row
    request.state.auth_session = auth_session
    request.state.current_user = user
    return user


async def get_current_user(
    user: Annotated[EnterpriseUser | None, Depends(get_optional_user)],
) -> EnterpriseUser:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_roles(*roles: str) -> Callable:
    async def dependency(
        user: Annotated[EnterpriseUser, Depends(get_current_user)],
    ) -> EnterpriseUser:
        if user.system_role not in roles:
            raise HTTPException(status_code=403, detail="当前角色无权执行此操作")
        return user

    return dependency


__all__ = [
    "get_session",
    "get_optional_user",
    "get_current_user",
    "require_roles",
    "utc_now",
]
