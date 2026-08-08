"""Evaluation endpoints (PLAN 3/5): cases + runs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseOut,
    EvaluationRunCreate,
    EvaluationRunOut,
)
from app.services.task_system import enqueue_job
from app.utils.id import eval_id

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


@router.post("/evaluation-cases", response_model=EvaluationCaseOut)
async def create_case(body: EvaluationCaseCreate, session: AsyncSession = Depends(_gs)) -> EvaluationCaseOut:
    case = EvaluationCase(id=eval_id(), **body.model_dump())
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return EvaluationCaseOut.model_validate(case)


@router.get("/evaluation-cases", response_model=list[EvaluationCaseOut])
async def list_cases(kb_id: str, session: AsyncSession = Depends(_gs)) -> list[EvaluationCaseOut]:
    res = await session.execute(
        select(EvaluationCase).where(EvaluationCase.kb_id == kb_id).order_by(EvaluationCase.created_at)
    )
    return [EvaluationCaseOut.model_validate(c) for c in res.scalars().all()]


@router.post("/evaluation-runs", response_model=EvaluationRunOut)
async def create_run(body: EvaluationRunCreate, session: AsyncSession = Depends(_gs)) -> EvaluationRunOut:
    run = EvaluationRun(id=eval_id(), kb_id=body.kb_id, mode=body.mode, status="running", case_count=0)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await enqueue_job(
        session, "eval", body.kb_id, payload={"run_id": run.id, "case_ids": body.case_ids}
    )
    return EvaluationRunOut.model_validate(run)


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRunOut)
async def get_run(run_id: str, session: AsyncSession = Depends(_gs)) -> EvaluationRunOut:
    run = (await session.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return EvaluationRunOut.model_validate(run)
