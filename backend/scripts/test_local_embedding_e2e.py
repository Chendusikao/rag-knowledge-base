"""E2E: real local BGE-M3 embeddings flow through index -> dense store -> retrieve.

Run from the backend dir (loads .env => local embedding provider):
    cd backend && .venv/Scripts/python.exe scripts/test_local_embedding_e2e.py

First run downloads BGE-M3 (~2.3GB). Set HF_ENDPOINT=https://hf-mirror.com in CN.

Asserts:
  * INDEX job completes and produces chunks
  * the dense store (Chroma) is populated 1:1 with chunks
  * LocalEmbedding emits 1024-dim vectors
  * a cat-related query surfaces the cat section on top (real semantic retrieval)
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy import select

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# HuggingFace endpoint: only fall back to the China mirror when the user has not
# set HF_ENDPOINT explicitly. In this environment the mirror was unreachable while
# the official huggingface.co worked, so we default to the official endpoint.
os.environ.setdefault("HF_ENDPOINT", "https://huggingface.co")

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.common import DocStatus, JobStatus, JobType
from app.models.document import Document
from app.models.job import JobRun
from app.models.knowledge_base import KnowledgeBase
from app.services.providers.local_embedding import LocalEmbedding
from app.services.retrieval.dense_store import get_store
from app.services.retrieval.manager import retrieve
from app.services.task_system import enqueue_job, run_worker_once
from app.utils.hash import sha256_file
from app.utils.id import doc_id, kb_id

MD = """# 知识库示例

本知识库包含两个互不相关的主题。

## 猫咪的饮食习惯

猫是肉食动物，最喜欢吃的天然食物是鱼肉。小猫也爱吃虾和鸡肉。
养猫的人通常会购买猫粮，其中富含牛磺酸。

## 数据库索引

PostgreSQL 使用 B-Tree 索引加速查询。为频繁过滤的列建立索引可以显著提升性能。
稠密向量检索则依赖嵌入模型将文本映射为高维向量。
"""


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        # 1) KB
        kb = KnowledgeBase(id=kb_id(), name="emb-e2e-kb", description="local embedding e2e")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        print(f"[1] created KB {kb.id}")

        # 2) write markdown into KB storage
        kb_dir = settings.kb_storage_path / kb.id
        kb_dir.mkdir(parents=True, exist_ok=True)
        d_id = doc_id()
        d_dir = kb_dir / d_id
        d_dir.mkdir(parents=True, exist_ok=True)
        fpath = d_dir / "original.md"
        fpath.write_text(MD, encoding="utf-8")
        doc = Document(
            id=d_id, kb_id=kb.id, filename="sample.md", mime_type="text/markdown",
            ext=".md", content_hash=sha256_file(str(fpath)), size_bytes=fpath.stat().st_size,
            status=DocStatus.PENDING, storage_path=str(fpath),
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        print(f"[2] created Document {doc.id}")

        # 3) enqueue INDEX job + drain worker
        job = await enqueue_job(
            session, JobType.INDEX, kb.id, doc_id=doc.id,
            payload={"storage_path": str(fpath), "ext": ".md"},
        )
        print(f"[3] enqueued job {job.id}")
        handlers = __import__("app.services.worker_handlers", fromlist=["HANDLERS"]).HANDLERS
        for _ in range(15):
            await run_worker_once("emb-e2e-worker", handlers)
            jb = (await session.execute(
                select(JobRun).where(JobRun.id == job.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if jb.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                print(f"[3b] job status: {jb.status}")
                if jb.error:
                    print("job error:", jb.error[:500])
                break
        else:
            raise RuntimeError("index job did not finish within 15 worker passes")

        # 4) verify chunks + dense store population
        chunks = (await session.execute(select(Chunk).where(Chunk.kb_id == kb.id))).scalars().all()
        print(f"[4] chunks indexed: {len(chunks)}")
        assert chunks, "no chunks were produced"
        fresh_kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id).execution_options(populate_existing=True)
        )).scalar_one()
        store = get_store()
        dense_count = store.count(kb.id, fresh_kb.current_generation)
        print(
            f"[4b] dense vectors for gen {fresh_kb.current_generation}: "
            f"{dense_count} (backend={store.__class__.__name__})"
        )
        assert dense_count == len(chunks), "dense count must match indexed chunks"

        # 4c) dimension sanity
        v = await LocalEmbedding(model_name="BAAI/bge-m3").embed(["测试维度"])
        print(f"[4c] embed dim = {len(v[0])}")
        assert len(v[0]) == 1024, "BGE-M3 must emit 1024-dim vectors"

        # 5) real semantic retrieval: a cat query should surface the cat section
        res = await retrieve(session, kb.id, "猫最爱吃什么食物", mode="balanced")
        print(f"[5] retrieval results: {len(res.results)} (latency {res.latency_ms}ms)")
        assert res.results, "retrieval returned nothing"
        top_snip = res.results[0].snippet
        print(f"[5b] top snippet: {top_snip[:80]}")
        assert "猫" in top_snip or "鱼" in top_snip, f"expected cat topic on top, got: {top_snip[:80]}"

        print("\nLOCAL_EMBEDDING_E2E_OK")


if __name__ == "__main__":
    asyncio.run(main())
