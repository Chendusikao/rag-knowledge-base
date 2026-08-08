"""Reciprocal Rank Fusion (PLAN: RRF 融合).

Combines multiple ranked result lists (BM25, Dense, ...) into one ranking via:
    score(c) = sum_over_lists 1 / (k + rank(c))
where rank is 1-based. Robust to differently-scaled scores across modalities.
"""
from __future__ import annotations

from collections import defaultdict


def rrf(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """ranked_lists: each is a list of (chunk_id, score) ordered best-first."""
    fused: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (cid, _score) in enumerate(ranked, start=1):
            fused[cid] += 1.0 / (k + rank)
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return ordered
