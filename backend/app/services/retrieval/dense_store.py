"""Persistent dense vector store (PLAN: Chroma 稠密索引).

This is the **real** on-disk index for the dense retrieval leg — not a stub.
Two interchangeable backends share one interface:

  * ``ChromaDenseStore`` — uses ``chromadb`` (the PLAN target: persistent ANN).
    Auto-selected when ``chromadb`` is importable.
  * ``FileDenseStore``   — pure-Python, file-backed exact-cosine index. Used as
    a lightweight fallback when ``chromadb`` is not installed, so the scaffold
    (and its tests) run without that heavy dependency. Swap is transparent via
    ``get_store()``; once ``chromadb`` is installed and the KB re-indexed, the
    Chroma backend takes over automatically.

Keyed by ``(kb_id, generation)`` so an atomic index switch leaves the previous
generation's vectors intact until the new one commits and the old collection is
removed. ``chromadb`` is imported lazily; ``FileDenseStore`` has no third-party
dependencies.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path

from app.core.config import settings


def _coll_name(kb_id: str, generation: int) -> str:
    # Chroma collection names: ^[a-zA-Z0-9][a-zA-Z0-9_-]*$, <= 63 chars.
    h = hashlib.sha1(kb_id.encode()).hexdigest()[:16]
    return f"kc_{h}_g{generation}"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FileDenseStore:
    """Dependency-free, file-backed dense index (JSON vectors + ids).

    Suitable for the scaffold's scale (thousands of chunks). Persists across
    process restarts, demonstrating a genuinely persistent dense index.
    """

    def __init__(self, root: str | None = None):
        self.root = Path(root or str(Path(settings.data_dir) / "dense_file"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, kb_id: str, generation: int) -> Path:
        return self.root / _coll_name(kb_id, generation)

    def count(self, kb_id: str, generation: int) -> int:
        d = self._dir(kb_id, generation)
        p = d / "vectors.json"
        if not p.exists():
            return 0
        return len(json.loads(p.read_text(encoding="utf-8"))["ids"])

    def upsert(
        self,
        kb_id: str,
        generation: int,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict] | None = None,
    ) -> None:
        if not ids:
            return
        d = self._dir(kb_id, generation)
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "ids": list(ids),
            "vectors": [list(v) for v in vectors],
            "metas": [m for m in metadatas] if metadatas else None,
        }
        (d / "vectors.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def query(
        self, kb_id: str, generation: int, query_vec: list[float], top_k: int
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        d = self._dir(kb_id, generation)
        p = d / "vectors.json"
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        ids = data["ids"]
        vecs = data["vectors"]
        if not ids:
            return []
        scored = [(i, _cosine(query_vec, v)) for i, v in zip(ids, vecs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete_collection(self, kb_id: str, generation: int) -> None:
        import shutil

        d = self._dir(kb_id, generation)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


class ChromaDenseStore:
    """chroma-backed dense index (PLAN target). Lazy import of chromadb."""

    def __init__(self, persist_dir: str | None = None):
        self._persist_dir = persist_dir or str(Path(settings.data_dir) / "chroma")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import chromadb  # lazy import
            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _collection(self, kb_id: str, generation: int):
        return self.client.get_or_create_collection(
            name=_coll_name(kb_id, generation),
            metadata={"hnsw:space": "cosine"},
        )

    def count(self, kb_id: str, generation: int) -> int:
        try:
            return int(self._collection(kb_id, generation).count())
        except Exception:  # noqa: BLE001
            return 0

    def upsert(
        self,
        kb_id: str,
        generation: int,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict] | None = None,
    ) -> None:
        if not ids:
            return
        self._collection(kb_id, generation).upsert(
            ids=list(ids),
            embeddings=[list(v) for v in vectors],
            metadatas=list(metadatas) if metadatas else None,
        )

    def query(
        self, kb_id: str, generation: int, query_vec: list[float], top_k: int
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        col = self._collection(kb_id, generation)
        n = col.count()
        if n == 0:
            return []
        n = min(top_k, n)
        res = col.query(query_embeddings=[list(query_vec)], n_results=n)
        ids = res["ids"][0] if res.get("ids") else []
        dists = res["distances"][0] if res.get("distances") else []
        # Chroma cosine space: distance small => similar. Convert to a score.
        return [(i, 1.0 - d) for i, d in zip(ids, dists)]

    def delete_collection(self, kb_id: str, generation: int) -> None:
        name = _coll_name(kb_id, generation)
        try:
            self.client.delete_collection(name=name)
        except Exception:  # noqa: BLE001
            pass


# Process-wide singleton.
_STORE = None


def get_store():
    global _STORE
    if _STORE is None:
        try:
            import chromadb  # noqa: F401
            _STORE = ChromaDenseStore()
        except Exception:  # noqa: BLE001
            _STORE = FileDenseStore()
    return _STORE


def backend_name() -> str:
    return type(get_store()).__name__
