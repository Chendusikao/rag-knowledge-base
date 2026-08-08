"""Job status polling (PLAN 3: GET /api/v1/jobs/{id})."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.models.job import JobRun
from app.schemas.job import JobRunOut

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRunOut)
async def get_job(job_id: str, session: AsyncSession = Depends(_gs)) -> JobRunOut:
    job = (await session.execute(select(JobRun).where(JobRun.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobRunOut.model_validate(job)

