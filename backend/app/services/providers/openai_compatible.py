"""OpenAI-compatible provider (PLAN 3 "通用 OpenAI-compatible Provider").

Implements EmbeddingProvider + LLMProvider. The same endpoint shape covers
OpenAI, vLLM, Ollama, Azure OpenAI, and most local model servers.

Secret resolution goes through ``secret_store.get_secret`` (Windows Credential
Manager integration is the planned real backend). If no secret is configured the
calls fail with a clear error rather than leaking anything.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.services.providers.base import (
    AgentProvider,
    AnswerResult,
    EmbeddingProvider,
    LLMProvider,
)
from app.services.providers.secret_store import get_secret


class OpenAICompatibleProvider(EmbeddingProvider, LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        credential_ref: str | None = None,
        api_key: str | None = None,
        dim: int = 1024,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.credential_ref = credential_ref
        self._api_key = api_key
        self.dim = dim
        self.timeout = timeout

    @property
    def api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        return get_secret(self.credential_ref)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        key = self.api_key
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.base_url:
            raise RuntimeError("OpenAI-compatible provider requires base_url")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            # Sort by index to preserve order.
            data.sort(key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in data]

    async def complete(self, system: str, user: str, **kwargs) -> str:
        if not self.base_url:
            raise RuntimeError("OpenAI-compatible provider requires base_url")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        body: dict = {"model": self.model, "messages": messages}
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def stream(self, system: str, user: str, **kwargs) -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        body = {"model": self.model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions",
                headers=self._headers(), json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if tok := delta.get("content"):
                        yield tok


class OpenAICompatibleAgent(AgentProvider):
    """Thin AgentProvider wrapper that uses the chat endpoint for answering."""

    def __init__(self, base: OpenAICompatibleProvider):
        self.base = base

    async def answer(self, context_bundle: dict, query: str, *, system=None) -> AnswerResult:
        ctx = context_bundle.get("context_text", "")
        citations = context_bundle.get("citations", [])
        user = f"参考资料：\n{ctx}\n\n问题：{query}\n请基于参考资料回答，并在结论中引用来源。"
        answer = await self.base.complete(system or "你是严谨的检索增强助手。", user)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=0.8 if citations else 0.2,
            insufficient_evidence=not citations,
        )
