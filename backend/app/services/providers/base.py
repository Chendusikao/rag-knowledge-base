"""Provider abstraction layer (PLAN 3 "供应商接口").

Four provider roles:
  * EmbeddingProvider  — text -> dense vector (Qwen3-Embedding-0.6B locally)
  * LLMProvider        — chat / completion (OpenAI-compatible or local)
  * VisionProvider     — image -> description (OCR / VLM)
  * AgentProvider      — takes a context_bundle + query and returns the unified
                         answer structure (Dify Agent). MUST NOT bypass local
                         citation verification (PLAN 3).

The default ``mock`` implementations let the whole pipeline run with no GPU and
no cloud key. Swap in real providers via the factory / provider profiles.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class AnswerResult:
    answer: str
    citations: list[dict] = field(default_factory=list)  # each: {chunk_id, page_number, ...}
    confidence: float = 0.0
    insufficient_evidence: bool = False


class EmbeddingProvider(ABC):
    dim: int = 1024

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one dense vector per input text."""


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str, **kwargs) -> str:
        """Return a single completion."""

    async def stream(self, system: str, user: str, **kwargs) -> AsyncIterator[str]:
        """Yield tokens. Default falls back to a single complete() chunk."""
        yield await self.complete(system, user, **kwargs)


class VisionProvider(ABC):
    @abstractmethod
    async def describe(self, image_bytes: bytes, prompt: str = "") -> str:
        """Return a textual description / OCR result for an image."""


class AgentProvider(ABC):
    @abstractmethod
    async def answer(
        self, context_bundle: dict, query: str, *, system: Optional[str] = None
    ) -> AnswerResult:
        """Given retrieved context + query, produce the unified answer structure."""


class RerankProvider(ABC):
    @abstractmethod
    async def rerank(self, query: str, items: list[dict]) -> dict[str, float]:
        """Score each candidate passage for relevance to ``query``.

        ``items`` is a list of dicts with at least ``chunk_id`` and ``snippet``.
        Returns a mapping ``chunk_id -> float score`` (higher = more relevant).
        Implementations must be defensive: on any failure return an empty dict
        so the caller can keep the previous (RRF) ordering instead of crashing.
        """
