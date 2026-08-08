"""Verify the offline local-path BGE-M3 embedding (option A).

Loads ``LocalEmbedding`` from ``RAG_LOCAL_EMBEDDING_MODEL_PATH`` (if set & exists),
embeds Chinese/English samples, and checks:
  - dimension matches (1024 for BGE-M3)
  - semantically similar sentences have higher cosine than unrelated ones
  - vectors are L2-normalized

If the path is unset or missing, prints download instructions and exits 0 (skip),
so smoke runs don't fail in environments without weights.
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.providers.local_embedding import LocalEmbedding


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main():
    path = settings.local_embedding_model_path
    if not path:
        print("SKIP: RAG_LOCAL_EMBEDDING_MODEL_PATH 未设置。")
        print("  在能联网的环境下载 BGE-M3 后，于 .env 设置该路径并启用 provider=local。")
        sys.exit(0)
    if not Path(path).exists():
        print(f"SKIP: 路径不存在: {path}")
        print("  请先下载权重：huggingface-cli download BAAI/bge-m3 --local-dir <path>")
        sys.exit(0)

    print(f"Loading BGE-M3 from local path: {path}")
    emb = LocalEmbedding(model_path=path)
    print(f"  dim = {emb.dim}")

    async def run():
        texts = [
            "猫是一种很常见的家养宠物，喜欢抓老鼠和玩耍。",
            "小猫非常可爱，常被人们当作伴侣动物饲养。",
            "今天股市大跌，很多投资者损失惨重。",
            "股票价格受宏观经济和公司财报影响很大。",
            "The cat sat on the mat.",
            "A kitten is a young cat.",
        ]
        vecs = await emb.embed(texts)
        sim_cat = cosine(vecs[0], vecs[1])
        diff_cat = cosine(vecs[0], vecs[2])
        sim_en = cosine(vecs[4], vecs[5])
        diff_en = cosine(vecs[4], vecs[2])
        norm0 = math.sqrt(sum(x * x for x in vecs[0]))
        print(f"  向量数={len(vecs)} 每维={len(vecs[0])} L2范数={norm0:.4f}")
        print(f"  中文 猫<->小猫 余弦 = {sim_cat:.3f}")
        print(f"  中文 猫<->股票 余弦 = {diff_cat:.3f}")
        print(f"  英文 cat<->kitten 余弦 = {sim_en:.3f}")
        print(f"  英文 cat<->股票 余弦 = {diff_en:.3f}")
        ok = (
            len(vecs[0]) == emb.dim
            and abs(norm0 - 1.0) < 1e-3
            and sim_cat > diff_cat
            and sim_en > diff_en
        )
        print("PATH_OK" if ok else "PATH_FAIL")
        return 0 if ok else 1

    rc = asyncio.run(run())
    sys.exit(rc)


if __name__ == "__main__":
    main()
