"""Import all models so they register on Base.metadata for create_all / Alembic."""
from app.models.cache import CacheEntry
from app.models.chat import ChatSession, Citation, Message, RetrievalTrace
from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion
from app.models.evaluation import EvaluationCase, EvaluationRun, MetricResult
from app.models.job import JobRun
from app.models.knowledge_base import IndexGeneration, KnowledgeBase
from app.models.provider import ProviderProfile

__all__ = [
    "KnowledgeBase",
    "Document",
    "DocumentVersion",
    "Chunk",
    "IndexGeneration",
    "ChatSession",
    "Message",
    "Citation",
    "RetrievalTrace",
    "EvaluationCase",
    "EvaluationRun",
    "MetricResult",
    "JobRun",
    "ProviderProfile",
    "CacheEntry",
]
