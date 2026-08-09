"""Job status polling (PLAN 3: GET /api/v1/jobs/{id})."""
from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session as _gs
from app.models.enterprise import EnterpriseUser
from app.models.job import JobRun
from app.schemas.job import JobRunOut
from app.services.enterprise import require_kb_access

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRunOut)
async def get_job(
    job_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> JobRunOut:
    job = (await session.execute(select(JobRun).where(JobRun.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    await require_kb_access(session, user, job.kb_id, "viewer", request=request)
    return JobRunOut.model_validate(job)
