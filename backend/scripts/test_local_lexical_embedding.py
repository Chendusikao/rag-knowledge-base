"""Unit test for the zero-download LocalLexicalEmbedding provider.

Verifies:
  * correct dimensionality (settings.local_embedding_dim, default 1024)
  * determinism (same text -> identical vector)
  * L2 normalization (unit length)
  * similar Chinese / English sentences score higher cosine than unrelated ones
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.providers.lexical_embedding import LocalLexicalEmbedding


def cosine(a: list[float], b: list[float]) -> float:
    assert len(a) == len(b)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def main() -> None:
    emb = LocalLexicalEmbedding(dim=1024)

    # 1) dimensionality + batch shape
    vecs = await emb.embed(["你好世界", "hello world"])
    assert len(vecs) == 2 and all(len(v) == 1024 for v in vecs), "dim/shape mismatch"
    print("[ok] dim=1024, batch shape correct")

    # 2) determinism
    v1 = (await emb.embed(["机器学习很有趣"]))[0]
    v2 = (await emb.embed(["机器学习很有趣"]))[0]
    assert v1 == v2, "not deterministic"
    print("[ok] deterministic for identical text")

    # 3) L2 normalization
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-6, f"not unit length: {norm}"
    print(f"[ok] L2-normalized (norm={norm:.4f})")

    # 4) semantic-ish: similar vs unrelated (Chinese)
    cat_a = "猫是一种常见的家养宠物，喜欢抓老鼠"
    cat_b = "小猫很可爱，常被人类当作伴侣动物饲养"
    cat_unrelated = "股票市场今天大幅上涨，投资者纷纷买入"
    va, vb, vu = (await emb.embed([cat_a, cat_b, cat_unrelated]))
    sim_same = cosine(va, vb)
    sim_diff = cosine(va, vu)
    print(f"[info] 相似句余弦={sim_same:.4f}  无关句余弦={sim_diff:.4f}")
    assert sim_same > sim_diff, "similar should outscore unrelated"
    assert sim_same > 0.05, "similar Chinese sentences should have positive signal"
    print("[ok] similar Chinese sentences score higher than unrelated")

    # 5) English
    e1, e2, e3 = (await emb.embed([
        "the cat sat on the mat",
        "a kitten rested on the rug",
        "the stock market rose sharply today",
    ]))
    es = cosine(e1, e2)
    ed = cosine(e1, e3)
    print(f"[info] EN 相似={es:.4f}  无关={ed:.4f}")
    assert es > ed, "EN similar should outscore unrelated"
    print("[ok] similar English sentences score higher than unrelated")

    print("\nLEXICAL_EMBEDDING_OK")


if __name__ == "__main__":
    asyncio.run(main())
