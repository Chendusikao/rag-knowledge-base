"""Central registry of job handlers used by the worker(s)."""
from __future__ import annotations

from app.models.common import JobType
from app.services.evaluation import run_evaluation_job
from app.services.indexing import index_document_job

HANDLERS: dict[str, object] = {
    JobType.INDEX: index_document_job,
    JobType.REINDEX: index_document_job,
    JobType.EVAL: run_evaluation_job,
}
