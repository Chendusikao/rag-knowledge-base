"""Backend smoke test for the V1 scaffold (no HTTP server needed).

Exercises the core pipeline:
    create KB -> write a Markdown file -> enqueue INDEX job -> run worker
    -> BM25+Dense+RRF retrieve -> assert chunks + results exist.

Run with the backend venv:
    cd backend && .venv/Scripts/python.exe scripts/smoke.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.common import DocStatus, JobStatus, JobType
from app.models.job import JobRun
from app.services.retrieval.dense_store import get_store
from app.services.retrieval.manager import retrieve
from app.services.task_system import enqueue_job, run_worker_once
from app.models.common import JobStatus
from app.utils.hash import sha256_file
from app.utils.id import doc_id, kb_id


MD = """# 项目简介

这是一个用于演示的多模态 RAG 系统。

## 架构

系统由前端和后端组成。后端使用 FastAPI 与 SQLAlchemy。

## 检索

检索阶段结合 BM25 与稠密向量，并通过 RRF 融合，再用重排模型精排。

### BM25

BM25 是一种经典的稀疏检索算法，对关键词匹配非常有效。

### 稠密向量

稠密向量由嵌入模型生成，擅长语义匹配。

## 引用

回答会附带可点击的引用，定位到页码或章节。
"""


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        # 1) KB
        kb = KnowledgeBase(id=kb_id(), name="smoke-kb", description="smoke test")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        print(f"[1] created KB {kb.id}")

        # 2) write markdown into KB storage
        kb_dir = settings.kb_storage_path / kb.id
        kb_dir.mkdir(parents=True, exist_ok=True)
        doc_d = doc_id()
        doc_dir = kb_dir / doc_d
        doc_dir.mkdir(parents=True, exist_ok=True)
        fpath = doc_dir / "original.md"
        fpath.write_text(MD, encoding="utf-8")

        doc = Document(
            id=doc_d, kb_id=kb.id, filename="sample.md", mime_type="text/markdown",
            ext=".md", content_hash=sha256_file(str(fpath)), size_bytes=fpath.stat().st_size,
            status=DocStatus.PENDING, storage_path=str(fpath),
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        print(f"[2] created Document {doc.id}")

        # 3) enqueue INDEX job + drain worker until THIS job finishes
        job = await enqueue_job(session, JobType.INDEX, kb.id, doc_id=doc.id,
                                payload={"storage_path": str(fpath), "ext": ".md"})
        print(f"[3] enqueued job {job.id}")
        handlers = __import__("app.services.worker_handlers", fromlist=["HANDLERS"]).HANDLERS
        for _ in range(10):
            await run_worker_once("smoke-worker", handlers)
            jb = (await session.execute(
                select(JobRun).where(JobRun.id == job.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if jb.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                print(f"[3b] job status: {jb.status}")
                if jb.error:
                    print("job error:", jb.error[:500])
                break
        else:
            raise RuntimeError("index job did not finish within 10 worker passes")

        # 4) verify chunks + that the dense index was populated (re-read generation
        # because the worker bumped it in a separate session).
        chunks = (await session.execute(select(Chunk).where(Chunk.kb_id == kb.id))).scalars().all()
        print(f"[4] chunks indexed: {len(chunks)}")
        assert len(chunks) > 0, "no chunks were produced"
        fresh_kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id).execution_options(populate_existing=True)
        )).scalar_one()
        store = get_store()
        dense_count = store.count(kb.id, fresh_kb.current_generation)
        print(f"[4b] dense vectors for gen {fresh_kb.current_generation}: {dense_count} (backend={store.__class__.__name__})")
        assert dense_count == len(chunks), "dense count must match indexed chunks"

        # 5) retrieve
        res = await retrieve(session, kb.id, "BM25 是什么？", mode="balanced")
        print(f"[5] retrieval results: {len(res.results)} (latency {res.latency_ms}ms)")
        assert len(res.results) > 0, "retrieval returned nothing"
        assert res.context_bundle["context_text"], "empty context bundle"

        # 6) deep mode
        res2 = await retrieve(session, kb.id, "检索阶段如何融合？", mode="deep")
        print(f"[6] deep results: {len(res2.results)}")

        print("\nSMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
