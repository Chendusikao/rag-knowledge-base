"""Unit test: LocalEmbedding(BAAI/bge-m3) produces real 1024-dim semantic vectors.

Run from the backend dir with the project venv:
    cd backend && .venv/Scripts/python.exe scripts/test_local_embedding.py

First run downloads BGE-M3 weights (~2.3GB) from HuggingFace. In China the
download is much faster via the mirror, so we set HF_ENDPOINT automatically
unless it is already defined in the environment.
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
from pathlib import Path

# Make the backend package importable when run as a standalone script
# (e.g. .venv/Scripts/python.exe scripts/test_local_embedding.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# HuggingFace endpoint: only fall back to the China mirror when the user has not
# set HF_ENDPOINT explicitly. In this environment the mirror was unreachable while
# the official huggingface.co worked, so we default to the official endpoint.
os.environ.setdefault("HF_ENDPOINT", "https://huggingface.co")

from app.services.providers.local_embedding import LocalEmbedding


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def main() -> None:
    emb = LocalEmbedding(model_name="BAAI/bge-m3")
    texts = [
        "猫咪最喜欢吃鱼肉",
        "小猫爱吃鱼和虾",
        "今天天气晴朗，适合去户外跑步锻炼",
        "后端使用 FastAPI 与 SQLAlchemy 构建 REST API",
    ]
    print("Loading BGE-M3 and embedding 4 sentences (first load may take a minute)…")
    vecs = await emb.embed(texts)
    assert len(vecs) == 4, "expected 4 vectors"

    dim = len(vecs[0])
    print(f"dim = {dim}")
    assert dim == 1024, f"expected 1024-dim, got {dim}"

    norms = [round(math.sqrt(sum(x * x for x in v)), 4) for v in vecs]
    print(f"norms = {norms}  (should all be ~1.0 -> unit-normalized)")
    assert all(abs(n - 1.0) < 1e-3 for n in norms), "vectors must be normalized"

    sim_cat = _cosine(vecs[0], vecs[1])
    sim_weather = _cosine(vecs[0], vecs[2])
    sim_api = _cosine(vecs[0], vecs[3])
    print(f"sim(cat, cat)      = {sim_cat:.4f}")
    print(f"sim(cat, weather)  = {sim_weather:.4f}")
    print(f"sim(cat, fastapi)  = {sim_api:.4f}")

    assert sim_cat > sim_weather, "semantically similar pair must score higher"
    assert sim_cat > sim_api, "semantically similar pair must score higher"
    print("\nLOCAL_EMBEDDING_OK")


if __name__ == "__main__":
    asyncio.run(main())
