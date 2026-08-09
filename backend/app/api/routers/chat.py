"""Chat streaming endpoint (PLAN 3: POST /api/v1/chat/stream, SSE)."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session as _gs
from app.models.enterprise import EnterpriseUser, KnowledgeBaseScope
from app.schemas.chat import ChatRequest, RetrievalMode
from app.services.chat_service import stream_answer
from app.services.audit import record_audit
from app.services.enterprise import require_kb_access
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["chat"])


async def _event_stream(req: ChatRequest, session: AsyncSession):
    async for event in stream_answer(
        session,
        kb_id=req.kb_id,
        query=req.query,
        mode=req.mode.value if isinstance(req.mode, RetrievalMode) else req.mode,
        filters=req.filters,
        backend=req.backend,
        sid=req.session_id,
    ):
        yield f"data: {event.model_dump_json()}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(_gs)],
    user: Annotated[EnterpriseUser, Depends(get_current_user)],
) -> StreamingResponse:
    await require_kb_access(session, user, req.kb_id, "viewer", request=request)
    scope = (
        await session.execute(
            select(KnowledgeBaseScope).where(KnowledgeBaseScope.kb_id == req.kb_id)
        )
    ).scalar_one_or_none()
    await record_audit(
        session,
        actor=user,
        action="chat.queried",
        resource_type="knowledge_base",
        resource_id=req.kb_id,
        department_id=scope.department_id if scope else None,
        details={
            "query_length": len(req.query),
            "mode": req.mode.value if isinstance(req.mode, RetrievalMode) else req.mode,
            "backend": req.backend,
        },
        request=request,
    )
    await session.commit()
    return StreamingResponse(
        _event_stream(req, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
