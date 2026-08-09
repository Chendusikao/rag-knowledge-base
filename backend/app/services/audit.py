"""Append-only audit recording with sensitive-value minimization."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import AuditEvent, EnterpriseUser
from app.utils.id import audit_id


_SENSITIVE_KEYS = {
    "password",
    "temporary_password",
    "current_password",
    "new_password",
    "token",
    "session",
    "api_key",
    "credential",
    "query",
    "content",
}


def _safe_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    result: dict[str, Any] = {}
    for key, value in details.items():
        lowered = key.lower()
        if any(secret in lowered for secret in _SENSITIVE_KEYS):
            result[key] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        else:
            result[key] = str(value)[:500]
    return result


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    actor: EnterpriseUser | None = None,
    department_id: str | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=audit_id(),
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else "",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        department_id=department_id,
        outcome=outcome,
        request_id=getattr(request.state, "request_id", "") if request else "",
        ip_address=request.client.host[:64] if request and request.client else "",
        user_agent=(request.headers.get("user-agent", "")[:512] if request else ""),
        details=_safe_details(details),
    )
    session.add(event)
    await session.flush()
    return event
