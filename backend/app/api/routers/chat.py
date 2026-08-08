"""Chat streaming endpoint (PLAN 3: POST /api/v1/chat/stream, SSE)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _gs
from app.schemas.chat import ChatRequest, RetrievalMode
from app.services.chat_service import stream_answer

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
async def chat_stream(req: ChatRequest, session: AsyncSession = Depends(_gs)) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(req, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
