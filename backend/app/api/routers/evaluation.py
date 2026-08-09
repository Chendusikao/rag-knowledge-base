"""Evaluation endpoints (PLAN 3/5): cases + runs."""
from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session as _gs
from app.models.enterprise import EnterpriseUser
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseOut,
    EvaluationRunCreate,
    EvaluationRunOut,
)
from app.services.task_system import enqueue_job
from app.utils.id import eval_id
from app.services.enterprise import require_kb_access

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


@router.post("/evaluation-cases", response_model=EvaluationCaseOut)
async def create_case(
    body: EvaluationCaseCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> EvaluationCaseOut:
    await require_kb_access(session, user, body.kb_id, "manager", request=request)
    case = EvaluationCase(id=eval_id(), **body.model_dump())
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return EvaluationCaseOut.model_validate(case)


@router.get("/evaluation-cases", response_model=list[EvaluationCaseOut])
async def list_cases(
    kb_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> list[EvaluationCaseOut]:
    await require_kb_access(session, user, kb_id, "manager", request=request)
    res = await session.execute(
        select(EvaluationCase).where(EvaluationCase.kb_id == kb_id).order_by(EvaluationCase.created_at)
    )
    return [EvaluationCaseOut.model_validate(c) for c in res.scalars().all()]


@router.post("/evaluation-runs", response_model=EvaluationRunOut)
async def create_run(
    body: EvaluationRunCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> EvaluationRunOut:
    await require_kb_access(session, user, body.kb_id, "manager", request=request)
    run = EvaluationRun(id=eval_id(), kb_id=body.kb_id, mode=body.mode, status="running", case_count=0)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await enqueue_job(
        session, "eval", body.kb_id, payload={"run_id": run.id, "case_ids": body.case_ids}
    )
    return EvaluationRunOut.model_validate(run)


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRunOut)
async def get_run(
    run_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> EvaluationRunOut:
    run = (await session.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    await require_kb_access(session, user, run.kb_id, "manager", request=request)
    return EvaluationRunOut.model_validate(run)
