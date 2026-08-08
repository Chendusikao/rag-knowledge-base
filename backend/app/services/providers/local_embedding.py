"""Local embedding provider via sentence-transformers (PLAN: real local embeddings).

Production-shaped path: load a local embedding model and produce real dense
vectors. **Optional** and **lazily imported** so sentence-transformers + torch
are not required to run the scaffold (the default ``mock`` / ``local-lexical``
providers keep the system GPU-free and download-free).

Two loading sources, in priority order:

  1. ``model_path`` — a local directory containing the model files (config
     ``RAG_LOCAL_EMBEDDING_MODEL_PATH``). Use this when model weights cannot be
     fetched from the internet (air-gapped / CDN-blocked). Sentence-Transformers
     loads the folder directly — no download.
  2. ``model_name`` — a HuggingFace model id (default ``BAAI/bge-m3``). On first
     load this downloads the weights once (~2.3GB) if not already cached.

Enable the offline (local-path) mode:

    RAG_DEFAULT_EMBEDDING_PROVIDER=local
    RAG_LOCAL_EMBEDDING_MODEL_PATH=/abs/path/to/bge-m3

Enable with auto-download (needs internet):

    RAG_DEFAULT_EMBEDDING_PROVIDER=local
    RAG_LOCAL_EMBEDDING_MODEL=BAAI/bge-m3

sentence-transformers is synchronous, so encoding runs in the default thread
pool to avoid blocking the asyncio event loop.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.services.providers.base import EmbeddingProvider


class LocalEmbedding(EmbeddingProvider):
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        model_path: str | None = None,
        dim: int = 1024,
    ):
        # Resolve a relative model_path against the backend root so a path like
        # "models/bge-m3" works regardless of the process cwd.
        if model_path:
            p = Path(model_path)
            if not p.is_absolute():
                p = (BACKEND_ROOT / p).resolve()
            self.model_path = str(p)
        else:
            self.model_path = None
        self.model_name = model_name
        self.dim = dim
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy

            load_from = self.model_path or self.model_name
            self._model = SentenceTransformer(load_from)
            # Prefer the model's own embedding dimension; fall back to the
            # configured default when the model doesn't expose it.
            try:
                inferred = self._model.get_embedding_dimension()
                if inferred:
                    self.dim = inferred
            except Exception:  # noqa: BLE001
                pass
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        vecs = await loop.run_in_executor(
            None,
            lambda: self.model.encode(texts, normalize_embeddings=True),
        )
        return vecs.tolist()
