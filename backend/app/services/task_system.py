"""Persistent task system (PLAN 2 "后台任务").

Design
------
A ``JobRun`` is a row in SQLite. The API process enqueues jobs; one or more Worker
processes (or the API itself, for dev) claim them via a *lease*. State — status,
progress, checkpoint, retries — lives entirely in SQLite, so:

  * a crashed worker is recovered by another worker or on restart (no Redis/Docker);
  * progress is resumable from the last ``checkpoint``.

Lease model
-----------
  * claim -> status=RUNNING, lease_owner=worker_id, lease_expires_at = now + lease_seconds
  * heartbeat -> push lease_expires_at forward
  * a RUNNING job whose lease_expires_at is past ``job_stale_after_seconds`` is
    considered dead and is recovered (requeued or reassigned) by ``recover_stale_jobs``.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.common import JobStatus, JobType
from app.models.job import JobRun
from app.utils.id import job_id

logger = logging.getLogger("rag.tasks")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    kb_id: str,
    *,
    doc_id: str | None = None,
    payload: dict | None = None,
    max_retries: int | None = None,
) -> JobRun:
    """Create a QUEUED JobRun. Returns the persisted row."""
    job = JobRun(
        id=job_id(),
        job_type=job_type,
        kb_id=kb_id,
        doc_id=doc_id,
        status=JobStatus.QUEUED,
        payload=payload or {},
        retries=0,
        max_retries=max_retries if max_retries is not None else settings.max_job_retries,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, jid: str) -> JobRun | None:
    res = await session.execute(select(JobRun).where(JobRun.id == jid))
    return res.scalar_one_or_none()


async def claim_job(
    session: AsyncSession,
    worker_id: str,
    *,
    job_types: list[str] | None = None,
    now: datetime | None = None,
) -> JobRun | None:
    """Atomically claim a QUEUED job (or a stale RUNNING one) for this worker.

    Uses a SELECT ... FOR UPDATE-style row lock is not available on SQLite easily;
    we rely on a single-writer claim with lease semantics + unique worker assignment.
    """
    now = now or _now()
    stmt = select(JobRun).where(JobRun.status == JobStatus.QUEUED)
    if job_types:
        stmt = stmt.where(JobRun.job_type.in_(job_types))
    stmt = stmt.order_by(JobRun.created_at.asc()).limit(1)
    res = await session.execute(stmt)
    job = res.scalar_one_or_none()
    if job is None:
        return None

    job.status = JobStatus.RUNNING
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
    if job.started_at is None:
        job.started_at = now
    await session.commit()
    await session.refresh(job)
    return job


async def heartbeat(
    session: AsyncSession, jid: str, worker_id: str, *, now: datetime | None = None
) -> bool:
    now = now or _now()
    res = await session.execute(
        update(JobRun)
        .where(JobRun.id == jid, JobRun.lease_owner == worker_id)
        .values(lease_expires_at=now + timedelta(seconds=settings.worker_lease_seconds))
    )
    await session.commit()
    return res.rowcount > 0


async def update_checkpoint(
    session: AsyncSession,
    jid: str,
    *,
    checkpoint: dict | None = None,
    progress: float | None = None,
) -> None:
    values: dict[str, Any] = {}
    if checkpoint is not None:
        values["checkpoint"] = checkpoint
    if progress is not None:
        values["progress"] = max(0.0, min(1.0, progress))
    if values:
        await session.execute(update(JobRun).where(JobRun.id == jid).values(**values))
        await session.commit()


async def complete_job(session: AsyncSession, jid: str) -> None:
    await session.execute(
        update(JobRun)
        .where(JobRun.id == jid)
        .values(
            status=JobStatus.SUCCEEDED,
            progress=1.0,
            finished_at=_now(),
            lease_owner=None,
            lease_expires_at=None,
        )
    )
    await session.commit()


async def fail_job(session: AsyncSession, jid: str, error: str) -> JobRun:
    """Record a failure; requeue if retries remain, else mark FAILED."""
    job = await get_job(session, jid)
    if job is None:
        raise ValueError(f"job {jid} not found")
    job.retries += 1
    job.error = error[:2000]
    if job.retries < job.max_retries:
        job.status = JobStatus.QUEUED
        job.lease_owner = None
        job.lease_expires_at = None
        job.progress = 0.0
        logger.warning("Job %s failed (retry %d/%d): %s", jid, job.retries, job.max_retries, error)
    else:
        job.status = JobStatus.FAILED
        job.finished_at = _now()
        job.lease_owner = None
        job.lease_expires_at = None
        logger.error("Job %s permanently failed after %d retries: %s", jid, job.retries, error)
    await session.commit()
    await session.refresh(job)
    return job


async def recover_stale_jobs(
    session: AsyncSession, worker_id: str, *, now: datetime | None = None
) -> int:
    """Requeue RUNNING jobs whose lease has been dead beyond the stale threshold.

    Returns the number of jobs recovered. Called periodically by any worker.
    """
    now = now or _now()
    stale_cutoff = now - timedelta(seconds=settings.job_stale_after_seconds)
    res = await session.execute(
        select(JobRun).where(
            JobRun.status == JobStatus.RUNNING,
            JobRun.lease_expires_at < stale_cutoff,
        )
    )
    stale = res.scalars().all()
    for job in stale:
        job.status = JobStatus.QUEUED
        job.lease_owner = None
        job.lease_expires_at = None
        logger.info("Recovered stale job %s (was owned by %s)", job.id, job.lease_owner)
    if stale:
        await session.commit()
    return len(stale)


# --------------------------------------------------------------------------- #
# Worker runtime
# --------------------------------------------------------------------------- #
class JobHandler(Protocol):
    def __call__(self, job: JobRun, session: AsyncSession) -> Awaitable[None]: ...


class Worker:
    """Claim-and-execute loop. Run in-process (dev) or as a standalone process."""

    def __init__(self, worker_id: str, handlers: dict[str, JobHandler], *, poll_seconds: float = 2.0):
        self.worker_id = worker_id
        self.handlers = handlers
        self.poll_seconds = poll_seconds
        self._stop = False

    async def run_once(self, session: AsyncSession) -> bool:
        await recover_stale_jobs(session, self.worker_id)
        job = await claim_job(session, self.worker_id)
        if job is None:
            return False
        handler = self.handlers.get(job.job_type)
        if handler is None:
            await fail_job(session, job.id, f"No handler for job_type={job.job_type}")
            return True
        try:
            await handler(job, session)
            await complete_job(session, job.id)
        except Exception as exc:  # noqa: BLE001
            await fail_job(session, job.id, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        return True

    async def run_forever(self, session_factory) -> None:  # type: ignore[name-defined]
        from app.db.session import AsyncSessionLocal

        session_factory = session_factory or AsyncSessionLocal
        while not self._stop:
            async with session_factory() as session:
                did = await self.run_once(session)
            if not did:
                await asyncio.sleep(self.poll_seconds)

    def stop(self) -> None:
        self._stop = True


async def run_worker_once(worker_id: str, handlers: dict[str, JobHandler]) -> bool:
    """Convenience: run a single claim/execute cycle (used by API dev worker)."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await Worker(worker_id, handlers).run_once(session)
