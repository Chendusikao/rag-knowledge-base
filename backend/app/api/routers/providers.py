"""Provider profile endpoints (PLAN 3: PUT /provider-profiles/{role} and /test)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.models.provider import ProviderProfile
from app.schemas.provider import (
    ProviderProfileCreate,
    ProviderProfileOut,
    ProviderProfileUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)
from app.services.providers.factory import build_provider

router = APIRouter(prefix="/api/v1/provider-profiles", tags=["providers"])


async def _get_or_none(session: AsyncSession, role: str) -> ProviderProfile | None:
    return (
        await session.execute(select(ProviderProfile).where(ProviderProfile.role == role))
    ).scalar_one_or_none()


@router.get("", response_model=list[ProviderProfileOut])
async def list_providers(session: AsyncSession = Depends(_gs)) -> list[ProviderProfileOut]:
    res = await session.execute(select(ProviderProfile))
    return [ProviderProfileOut.model_validate(p) for p in res.scalars().all()]


@router.put("/{role}", response_model=ProviderProfileOut)
async def upsert_provider(
    role: str, body: ProviderProfileCreate, session: AsyncSession = Depends(_gs)
) -> ProviderProfileOut:
    if body.role and body.role != role:
        raise HTTPException(status_code=400, detail="role in body must match path")
    existing = await _get_or_none(session, role)
    data = body.model_dump()
    data["role"] = role
    if existing:
        for k, v in data.items():
            if v is not None:
                setattr(existing, k, v)
        prof = existing
    else:
        prof = ProviderProfile(id=f"pp_{role}", **data)
        session.add(prof)
    await session.commit()
    await session.refresh(prof)
    return ProviderProfileOut.model_validate(prof)


@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(req: ProviderTestRequest, session: AsyncSession = Depends(_gs)) -> ProviderTestResponse:
    """Cheap connectivity/capability check before persisting (PLAN PUT .../test)."""
    try:
        prof = ProviderProfile(
            role=req.role, kind=req.kind, base_url=req.base_url,
            model=req.model, credential_ref=req.credential_ref,
        )
        t0 = time.time()
        prov = build_provider(req.role, prof)
        # Minimal capability probe (mock always ok; real ones do a tiny call).
        capabilities: dict = {}
        if req.kind == "mock":
            ok = True
        elif req.kind == "openai_compatible":
            # Probe embedding with a 1-token input.
            emb = build_provider("embedding", prof)
            await emb.embed(["ping"])  # type: ignore[attr-defined]
            ok = True
            capabilities["embed"] = True
        elif req.kind == "dify":
            ok = bool(req.base_url and req.credential_ref)
        else:
            ok = False
        return ProviderTestResponse(
            ok=ok, latency_ms=int((time.time() - t0) * 1000),
            detail="ok" if ok else "check base_url / credential_ref", capabilities=capabilities,
        )
    except Exception as e:  # noqa: BLE001
        return ProviderTestResponse(ok=False, detail=f"{type(e).__name__}: {e}")
