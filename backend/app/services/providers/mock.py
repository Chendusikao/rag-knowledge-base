"""Mock providers — keep the whole pipeline runnable without GPU / cloud keys.

These produce *plausible* outputs so the API, streaming, citations and retrieval
lab all work end-to-end for development and demos. They are NOT for production
answer quality; swap to Qwen3 / OpenAI-compatible / Dify before evaluation.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator

from app.services.providers.base import (
    AnswerResult,
    AgentProvider,
    EmbeddingProvider,
    LLMProvider,
    VisionProvider,
)


class MockEmbedding(EmbeddingProvider):
    """Deterministic hashed bag-of-words vectors (dim 1024). Stub for real model."""

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = re.findall(r"\w+", text.lower())
        for t in toks:
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0
        # L2-normalize so cosine similarity is meaningful.
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class MockLLM(LLMProvider):
    """Synthesizes an answer from provided context (no real inference)."""

    async def complete(self, system: str, user: str, **kwargs) -> str:
        # The chat service builds `user` to include retrieved context snippets.
        # We echo a structured, citation-friendly answer for the scaffold.
        ctx = kwargs.get("context", "")
        if ctx:
            first = ctx.strip().split("\n")[0][:240]
            return (
                f"【Mock 回答】根据检索到的资料，最相关的片段是：{first}……\n"
                "（这是 Mock 生成器产出的占位回答，用于验证端到端链路；"
                "接入真实 LLM 后将替换为模型实际输出。）"
            )
        return "【Mock 回答】当前没有检索到足够的相关资料，无法给出依据充分的回答。"


class MockStreamLLM(MockLLM):
    async def stream(self, system: str, user: str, **kwargs) -> AsyncIterator[str]:
        text = await self.complete(system, user, **kwargs)
        for ch in text:
            yield ch


class MockVision(VisionProvider):
    async def describe(self, image_bytes: bytes, prompt: str = "") -> str:
        return "（Mock 视觉描述）图片内容占位；接入本地 OCR/VLM 或开启云端视觉解析后返回真实描述。"


class MockAgent(AgentProvider):
    """Wraps MockLLM to satisfy the AgentProvider contract."""

    def __init__(self) -> None:
        self._llm = MockLLM()

    async def answer(self, context_bundle: dict, query: str, *, system=None) -> AnswerResult:
        ctx = context_bundle.get("context_text", "")
        citations = context_bundle.get("citations", [])
        answer = await self._llm.complete(system or "", query, context=ctx)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=0.5 if citations else 0.1,
            insufficient_evidence=not citations,
        )
