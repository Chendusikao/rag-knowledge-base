"""Re-index every existing knowledge base with the current embedding provider.

Run this after switching ``RAG_DEFAULT_EMBEDDING_PROVIDER`` (e.g. from
``local-lexical`` to ``local`` BGE-M3) so all old vectors are regenerated.

The indexer uses KB-wide generation semantics: a single REINDEX job on any
document in the KB re-parses and re-embeds *all* documents of that KB.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.common import JobStatus, JobType
from app.models.document import Document
from app.models.job import JobRun
from app.models.knowledge_base import KnowledgeBase
from app.services.task_system import enqueue_job, run_worker_once
from app.services.worker_handlers import HANDLERS


async def reindex_all() -> None:
    async with AsyncSessionLocal() as session:
        # Find every KB that has at least one document stored on disk.
        kbs = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id.in_(
                        select(Document.kb_id).where(Document.storage_path != "")
                    )
                )
            )
        ).scalars().all()

        if not kbs:
            print("No knowledge bases with stored documents found; nothing to reindex.")
            return

        print(f"Found {len(kbs)} knowledge base(s) to reindex.")

        # Enqueue one REINDEX job per KB (using the first stored document as anchor).
        for kb in kbs:
            doc = (
                await session.execute(
                    select(Document).where(
                        Document.kb_id == kb.id, Document.storage_path != ""
                    )
                )
            ).scalars().first()
            if doc is None:
                continue
            job = await enqueue_job(
                session,
                JobType.REINDEX,
                kb_id=kb.id,
                doc_id=doc.id,
                payload={"storage_path": doc.storage_path, "ext": doc.ext},
            )
            print(f"  enqueued reindex for KB {kb.id} (job {job.id})")
        await session.commit()

    # Drain the job queue.
    print("Draining job queue...")
    worker_id = "reindex-cli"
    loop_total = 0
    while await run_worker_once(worker_id, HANDLERS):
        loop_total += 1
        print(f"  worker cycle #{loop_total} finished")

    # Report actual final DB state (robust to other workers also picking up jobs).
    async with AsyncSessionLocal() as session:
        counts = dict(
            (await session.execute(
                select(JobRun.status, func.count(JobRun.id)).group_by(JobRun.status)
            )).all()
        )
        print(
            f"Reindexed {len(kbs)} KB(s). "
            f"Job queue state: queued={counts.get(JobStatus.QUEUED, 0)} "
            f"running={counts.get(JobStatus.RUNNING, 0)} "
            f"succeeded={counts.get(JobStatus.SUCCEEDED, 0)} "
            f"failed={counts.get(JobStatus.FAILED, 0)}"
        )
        failed = (
            await session.execute(
                select(JobRun).where(JobRun.status == JobStatus.FAILED)
            )
        ).scalars().all()
        for job in failed:
            print(f"  FAILED job {job.id}: {job.error}")


if __name__ == "__main__":
    asyncio.run(reindex_all())
