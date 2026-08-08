"""FastAPI application entrypoint.

Wires routers, CORS, OpenAPI, DB init and an in-process task worker so the
scaffold runs end-to-end with a single `uvicorn app.main:app` (no separate
worker process or Docker required for development).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routers import (
    chat,
    documents,
    evaluation,
    jobs,
    knowledge_bases,
    providers,
    retrieval,
)
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.services.task_system import Worker
from app.services.worker_handlers import HANDLERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
    title="个人多模态 RAG 知识库问答系统",
    version="0.1.0",
    description="V1 地基脚手架：多知识库、混合检索、可点击引用、持久任务系统。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
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
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/meta", tags=["meta"])
async def meta() -> dict:
    """轻量运行状态：当前 LLM provider 与关键配置（供前端顶部状态条使用）。"""
    return {
        "llm_provider": settings.default_llm_provider,
        "deepseek_configured": bool(settings.deepseek_api_key),
        "doc_parser": settings.doc_parser,
    }


# 前端单页应用。挂载在最后，/api/* 路由优先级更高，现有接口不受影响。
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
