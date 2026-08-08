"""End-to-end test for the zero-download local-lexical embedding.

Verifies the full pipeline runs with RAG_DEFAULT_EMBEDDING_PROVIDER=local-lexical
(no model download): index a Chinese doc with distinct topics, populate the dense
store with real content-derived vectors, and confirm a topic query retrieves the
correct section at the top.

Run:
    cd backend && .venv/Scripts/python.exe scripts/test_local_lexical_e2e.py
"""
from __future__ import annotations

import asyncio
import sys
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
from app.utils.hash import sha256_file
from app.utils.id import doc_id, kb_id

MD = """# 知识库示例

本库用于验证本地词法向量检索。

## 猫

猫是一种常见的家养宠物，性格独立，喜欢抓老鼠，也常被人类当作伴侣动物饲养。小猫非常可爱。

## 股票

股票市场波动较大，投资者需要关注基本面与技术面，分散风险，避免追涨杀跌。

## 天气

天气预报可以提醒我们带伞，台风来临时要注意防风防汛。
"""


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        kb = KnowledgeBase(id=kb_id(), name="lexical-e2e", description="local lexical e2e")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        print(f"[1] KB {kb.id}")

        kb_dir = settings.kb_storage_path / kb.id
        kb_dir.mkdir(parents=True, exist_ok=True)
        d_id = doc_id()
        doc_dir = kb_dir / d_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        fpath = doc_dir / "original.md"
        fpath.write_text(MD, encoding="utf-8")

        doc = Document(
            id=d_id, kb_id=kb.id, filename="sample.md", mime_type="text/markdown",
            ext=".md", content_hash=sha256_file(str(fpath)), size_bytes=fpath.stat().st_size,
            status=DocStatus.PENDING, storage_path=str(fpath),
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        print(f"[2] Document {doc.id}")

        job = await enqueue_job(session, JobType.INDEX, kb.id, doc_id=doc.id,
                                payload={"storage_path": str(fpath), "ext": ".md"})
        print(f"[3] enqueued job {job.id}")
        handlers = __import__("app.services.worker_handlers", fromlist=["HANDLERS"]).HANDLERS
        for _ in range(10):
            await run_worker_once("lexical-worker", handlers)
            jb = (await session.execute(
                select(JobRun).where(JobRun.id == job.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if jb.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                print(f"[3b] job {jb.status}")
                if jb.error:
                    print("job error:", jb.error[:500])
                break
        else:
            raise RuntimeError("index job did not finish")

        chunks = (await session.execute(select(Chunk).where(Chunk.kb_id == kb.id))).scalars().all()
        print(f"[4] chunks: {len(chunks)}")
        assert len(chunks) > 0

        fresh_kb = (await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id).execution_options(populate_existing=True)
        )).scalar_one()
        store = get_store()
        dense_count = store.count(kb.id, fresh_kb.current_generation)
        print(f"[4b] dense vectors: {dense_count} (backend={store.__class__.__name__})")
        assert dense_count == len(chunks), "dense count must match chunks"

        # 5) retrieve a CAT query -> top result should be the cat section
        res = await retrieve(session, kb.id, "猫喜欢抓什么动物？", mode="balanced")
        print(f"[5] results: {len(res.results)} (latency {res.latency_ms}ms)")
        assert len(res.results) > 0
        top = res.results[0]
        print(f"[5b] top snippet: {top.snippet[:60]!r}")
        assert "猫" in top.snippet or "宠物" in top.snippet or "老鼠" in top.snippet, \
            "cat query should surface the cat section at the top"

        # 6) a STOCK query -> top should be the stock section (proves topic routing)
        res2 = await retrieve(session, kb.id, "投资股票要注意什么？", mode="balanced")
        top2 = res2.results[0]
        print(f"[6] top snippet: {top2.snippet[:60]!r}")
        assert "股票" in top2.snippet or "投资" in top2.snippet, "stock query should surface stock section"

        print("\nLEXICAL_E2E_OK")


if __name__ == "__main__":
    asyncio.run(main())
