"""BM25 sparse index (PLAN: BM25 稀疏索引).

Built in-memory per knowledge base from chunk text stored in SQLite. A
process-local cache keeps the index warm; it is keyed by (kb_id, generation) so
a new atomic index generation invalidates it automatically.
"""
from __future__ import annotations

import re
from collections import defaultdict

from rank_bm25 import BM25Okapi

# ASCII / digit words kept whole (so "BM25", "RAG", "FastAPI" match as units).
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
# Maximal runs of CJK ideographs — these must be split into character n-grams
# because \w+ would otherwise treat an entire Chinese sentence as a single token,
# making BM25 completely blind to Chinese (zero overlap -> no ranking signal).
_CJK_RUN_RE = re.compile(r"[一-鿿]+")


def tokenize(text: str) -> list[str]:
    """CJK-aware tokenizer: English/number words + Chinese char unigrams/bigrams.

    Without the CJK split, BM25 cannot retrieve Chinese at all — every chunk and
    query collapses to one giant token and matches nothing.
    """
    if not text:
        return []
    low = text.lower()
    toks: list[str] = list(_WORD_RE.findall(low))
    for run in _CJK_RUN_RE.findall(low):
        chars = list(run)
        toks.extend(chars)  # unigrams catch shared single characters
        for i in range(len(chars) - 1):
            toks.append(chars[i] + chars[i + 1])  # bigrams add precision
    return toks


class BM25Index:
    def __init__(self, chunk_ids: list[str], texts: list[str]):
        self.chunk_ids = chunk_ids
        self.corpus = [tokenize(t) for t in texts]
        if self.corpus:
            self._bm25 = BM25Okapi(self.corpus)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if self._bm25 is None or top_k <= 0:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        # Rank descending.
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.chunk_ids[i], float(scores[i])) for i in ranked]


# ---- Process-local cache keyed by (kb_id, generation) ----
_CACHE: dict[tuple[str, int], BM25Index] = {}


def get_bm25(kb_id: str, generation: int, chunk_ids: list[str], texts: list[str]) -> BM25Index:
    key = (kb_id, generation)
    if key not in _CACHE or len(_CACHE[key].chunk_ids) != len(chunk_ids):
        _CACHE[key] = BM25Index(chunk_ids, texts)
    return _CACHE[key]


def invalidate(kb_id: str, generation: int) -> None:
    _CACHE.pop((kb_id, generation), None)
