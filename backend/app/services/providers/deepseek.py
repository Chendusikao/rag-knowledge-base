"""DeepSeek provider (PLAN: real model integration).

DeepSeek exposes an OpenAI-compatible chat/embeddings API at
``https://api.deepseek.com``. We reuse ``OpenAICompatibleProvider`` for the
generation role, and add an **LLM-as-reranker** (``DeepSeekReranker``) that
scores the RRF-fused candidates with DeepSeek and reorders them.

Secrets come from ``RAG_DEEPSEEK_API_KEY`` (env / ``.env``), never hardcoded.
The reranker is fully optional: if it is disabled or its call fails, the caller
falls back to the existing RRF ordering so retrieval never breaks.
"""
from __future__ import annotations

import json
import re

from app.core.config import settings
from app.services.providers.base import RerankProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider

_UNSET: object = object()
_RERANKER: object = _UNSET  # cached singleton; None means "disabled"


def build_deepseek_llm() -> OpenAICompatibleProvider:
    """Build the DeepSeek LLM/Embedding provider from settings."""
    return OpenAICompatibleProvider(
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        timeout=90.0,
    )


_SYSTEM = (
    "You are a precise search-result reranker. Given a user query and several "
    "numbered passages, score each passage's relevance to the query as a float "
    "from 0.0 (irrelevant) to 1.0 (highly relevant). Respond with ONLY a JSON "
    "object that maps each passage number (as a string) to its score. No other text."
)


class DeepSeekReranker(RerankProvider):
    """Reorders RRF-fused candidates using DeepSeek as a cross-scorer."""

    def __init__(self, llm: OpenAICompatibleProvider | None = None):
        self._llm = llm

    @property
    def llm(self) -> OpenAICompatibleProvider:
        if self._llm is None:
            self._llm = build_deepseek_llm()
        return self._llm

    async def rerank(self, query: str, items: list[dict]) -> dict[str, float]:
        if not settings.deepseek_api_key or not items:
            return {}
        numbered = "\n".join(
            f"[{i}] {it.get('snippet', '')}" for i, it in enumerate(items)
        )
        user = (
            f"Query: {query}\n\nPassages:\n{numbered}\n\n"
            "Return the JSON scores for ALL passages."
        )
        try:
            raw = await self.llm.complete(_SYSTEM, user)
        except Exception:
            # Never let a provider error break retrieval.
            return {}
        return _parse_scores(raw, items)


def _parse_scores(raw: str, items: list[dict]) -> dict[str, float]:
    """Defensively extract ``{index: score}`` from a model response."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    scores: dict[str, float] = {}
    for key, val in obj.items():
        try:
            idx = int(key)
            if 0 <= idx < len(items):
                scores[items[idx]["chunk_id"]] = float(val)
        except (ValueError, KeyError, TypeError):
            continue
    return scores


def get_reranker() -> RerankProvider | None:
    """Return the configured reranker, or ``None`` to keep the RRF ordering.

    Enabled only when ``rerank_provider == "deepseek"`` AND a key is present.
    Cached as a singleton for the process lifetime.
    """
    global _RERANKER
    if _RERANKER is not _UNSET:
        return _RERANKER  # type: ignore[return-value]
    if settings.rerank_provider == "deepseek" and settings.deepseek_api_key:
        _RERANKER = DeepSeekReranker()
    else:
        _RERANKER = None
    return _RERANKER  # type: ignore[return-value]
