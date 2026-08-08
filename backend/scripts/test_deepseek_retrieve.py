"""Integration test: retrieve() invokes the DeepSeek reranker end-to-end.

Enables rerank_provider=deepseek + a (monkeypatched) DeepSeek completion, then
runs the real pipeline (index via worker -> retrieve) and asserts the RRF-fused
candidates are reordered by the reranker's scores. No real network call.
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.models.common import DocStatus, JobStatus, JobType
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.services.retrieval.manager import retrieve
from app.services.task_system import enqueue_job, run_worker_once
from app.utils.hash import sha256_file
from app.utils.id import doc_id, kb_id

# NOTE: run with shell env to enable the reranker (pydantic-settings reads it
# from the process environment, not from in-file os.environ overrides):
#   RAG_RERANK_PROVIDER=deepseek RAG_DEEPSEEK_API_KEY=sk-test \
#     .venv/Scripts/python.exe scripts/test_deepseek_retrieve.py


def _patch_complete() -> None:
    import json
    import re

    async def fake_complete(self, system, user, **kw):  # noqa: ANN001
        # Score every passage by its position: the LAST passage gets the highest
        # score. If the reranker is applied, that passage must move to the front.
        n = len(re.findall(r"\[(\d+)\]", user))
        return json.dumps({str(i): float(i) for i in range(n)})

    OpenAICompatibleProvider.complete = fake_complete  # type: ignore[assignment]


MD = """# 主题文档

这是一个用于演示的核心主题文档。

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
        kb = KnowledgeBase(id=kb_id(), name="ds-kb", description="deepseek rerank integration")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)

        kb_dir = settings.kb_storage_path / kb.id
        kb_dir.mkdir(parents=True, exist_ok=True)
        did = doc_id()
        doc_dir = kb_dir / did
        doc_dir.mkdir(parents=True, exist_ok=True)
        fpath = doc_dir / "original.md"
        fpath.write_text(MD, encoding="utf-8")

        doc = Document(
            id=did, kb_id=kb.id, filename="doc.md", mime_type="text/markdown",
            ext=".md", content_hash=sha256_file(str(fpath)), size_bytes=fpath.stat().st_size,
            status=DocStatus.PENDING, storage_path=str(fpath),
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        job = await enqueue_job(session, JobType.INDEX, kb.id, doc_id=doc.id,
                                payload={"storage_path": str(fpath), "ext": ".md"})
        handlers = __import__("app.services.worker_handlers", fromlist=["HANDLERS"]).HANDLERS
        for _ in range(10):
            await run_worker_once("ds-worker", handlers)
            jb = (await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb.id).execution_options(populate_existing=True)
            ))
            # Re-read job status with populate_existing (identity-map trap).
            from app.models.job import JobRun
            jrow = (await session.execute(
                select(JobRun).where(JobRun.id == job.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            _ = jb
            if jrow.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                assert jrow.status == JobStatus.SUCCEEDED, jrow.error
                break
        else:
            raise RuntimeError("index job did not finish")

        _patch_complete()
        # Balanced mode -> reranker active.
        result = await retrieve(session, kb.id, "核心主题是什么？", mode="balanced")
        assert len(result.results) > 0, "no retrieval results"
        n = len(result.results)
        scores = sorted(r.rerank_score for r in result.results)
        # The monkeypatched DeepSeek scored each passage by position (0..n-1),
        # so the sorted rerank scores must equal [0, 1, ..., n-1].
        assert scores == sorted(float(i) for i in range(n)), scores
        # Highest score (n-1) must be first after reranking (proves reranker applied).
        assert result.results[0].rerank_score == float(n - 1), "reranker did not order by score"
        print("RETRIEVE_RERANK_OK top_score=%.1f results=%d" % (
            result.results[0].rerank_score, n))
    print("ALL_DEEPSEEK_RETRIEVE_OK")


if __name__ == "__main__":
    asyncio.run(main())
