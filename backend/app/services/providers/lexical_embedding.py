"""Zero-download local embedding provider (lexical / content-derived).

Why this exists
---------------
The production-shaped path is :class:`LocalEmbedding` (sentence-transformers +
a real semantic model such as BGE-M3). That requires downloading several hundred
MB of weights, which is impossible in some sandboxed / offline networks (the
HuggingFace LFS, hf-mirror and ModelScope CDNs all return 404 there).

``LocalLexicalEmbedding`` is an **honest, dependency-free fallback** that still
produces *real* content-derived vectors (not random):

  * English / digit runs  -> word tokens
  * Chinese runs           -> character bigrams + trigrams  (the standard,
                             segmentation-free baseline for Chinese IR)
  * each feature is mapped to a signed slot in a fixed-dim space via a stable
    MD5 hash (hashing trick), accumulated with sublinear TF, then L2-normalized.

Texts that share words / character n-grams get high cosine similarity; unrelated
texts do not. This makes the dense store and the RRF / rerank pipeline operate on
a genuine lexical signal instead of noise.

IMPORTANT: this is **lexical**, not **semantic**. It will not match synonyms
("猫" vs "小猫") the way a trained embedding model would. It is the right choice
when you cannot download weights and still want a self-contained, runnable system.
Switch ``RAG_DEFAULT_EMBEDDING_PROVIDER=local`` (BGE-M3) the moment weights are
downloadable.

Enable with::

    RAG_DEFAULT_EMBEDDING_PROVIDER=local-lexical
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from app.services.providers.base import EmbeddingProvider

# English / digit words (length >= 2 to skip noisy single chars).
_WORD_RE = re.compile(r"[a-zA-Z0-9]{2,}")
# Maximal runs of CJK ideographs.
_CJK_RUN_RE = re.compile(r"[一-鿿]+")


def _tokenize(text: str) -> list[str]:
    """Segment text into lexical features (word tokens + CJK n-grams).

    For CJK runs we emit unigrams + bigrams + trigrams. Unigrams matter: a shared
    topic character (e.g. 猫) produces a common feature even when its surrounding
    context differs, so topically similar sentences still overlap. Bigrams/trigrams
    add precision and disambiguation.
    """
    if not text:
        return []
    low = text.lower()
    feats: list[str] = list(_WORD_RE.findall(low))
    for run in _CJK_RUN_RE.findall(low):
        chars = list(run)
        n = len(chars)
        # unigrams — catch shared single characters across different contexts
        feats.extend(chars)
        # bigrams
        for i in range(n - 1):
            feats.append("".join(chars[i : i + 2]))
        # trigrams
        for i in range(n - 2):
            feats.append("".join(chars[i : i + 3]))
    return feats


def _slot(token: str, dim: int) -> tuple[int, int]:
    """Map a token to a stable (index, sign) via MD5 (hashing trick)."""
    h = hashlib.md5(token.encode("utf-8")).digest()
    idx = int.from_bytes(h[:4], "big") % dim
    sign = 1 if (int.from_bytes(h[4:8], "big") & 1) == 0 else -1
    return idx, sign


class LocalLexicalEmbedding(EmbeddingProvider):
    """Deterministic, offline, content-derived dense embedding (lexical)."""

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tf: dict[str, int] = {}
        for tok in _tokenize(text):
            tf[tok] = tf.get(tok, 0) + 1
        if not tf:
            return vec
        for tok, count in tf.items():
            idx, sign = _slot(tok, self.dim)
            # sublinear TF keeps very frequent features from dominating.
            vec[idx] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]
