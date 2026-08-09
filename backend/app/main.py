"""FastAPI application entrypoint.

Wires routers, CORS, OpenAPI, DB init and an in-process task worker so the
scaffold runs end-to-end with a single `uvicorn app.main:app` (no separate
worker process or Docker required for development).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routers import (
    chat,
    auth,
    documents,
    enterprise,
    evaluation,
    jobs,
    knowledge_bases,
    providers,
    retrieval,
    source_library,
)
from app.core.config import settings
from app.core.security_middleware import RequestSecurityMiddleware
from app.api.deps import require_roles
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.services.task_system import Worker
from app.services.enterprise import prepare_enterprise_state
from app.models.enterprise import EnterpriseUser
from app.services.worker_handlers import HANDLERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await prepare_enterprise_state(session)
    logger.info("DB initialized at %s", settings.sqlite_url)
    # In-process worker: claims queued jobs and runs handlers.
    worker = Worker("api-inproc", HANDLERS, poll_seconds=2.0)
    task = asyncio.create_task(worker.run_forever(AsyncSessionLocal))
    try:
        yield
    finally:
        worker.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="企业多模态 RAG 知识库问答系统",
    version="0.2.0",
    description="企业 V1：部门知识库、角色权限、审计追踪、多模态检索与可点击引用。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestSecurityMiddleware)

for r in (
    auth.router,
    enterprise.router,
    source_library.router,
    knowledge_bases.router,
    documents.router,
    jobs.router,
    chat.router,
    retrieval.router,
    evaluation.router,
    providers.router,
):
    app.include_router(r)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/api/v1/meta", tags=["meta"])
async def meta(
    _: Annotated[EnterpriseUser, Depends(require_roles("admin"))],
) -> dict:
    """轻量运行状态：当前 LLM provider 与关键配置（供前端顶部状态条使用）。"""
    return {
        "llm_provider": settings.default_llm_provider,
        "deepseek_configured": bool(settings.deepseek_api_key),
        "doc_parser": settings.doc_parser,
    }


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """后端根路径仅作为开发入口，正式用户界面运行在 localhost:3000。"""
    return RedirectResponse(url="/docs")
