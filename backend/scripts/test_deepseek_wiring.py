"""Offline wiring test for the DeepSeek integration (no real API calls).

Runs in three modes selected by TEST_MODE:
  llm      — verify default_llm_provider=deepseek builds the DeepSeek LLM and
             that streaming works (with a monkeypatched completion).
  rerank   — verify DeepSeekReranker parses scores and reorders candidates, and
             degrades to {} on errors.
  disabled — verify get_reranker() is None when rerank_provider != deepseek.

Env vars are set at the very top, BEFORE importing app modules, so pydantic
settings pick them up in a fresh process.
"""
from __future__ import annotations

import asyncio
import os
import sys

MODE = os.environ.get("TEST_MODE", "llm")


def _patch_llm():
    from app.services.providers.openai_compatible import OpenAICompatibleProvider

    async def fake_complete(self, system, user, **kw):  # noqa: ANN001
        # Simulate a DeepSeek response: a JSON object mapping passage -> score.
        return '```json\n{"0": 0.9, "1": 0.1, "2": 0.5}\n```'

    async def fake_stream(self, system, user, **kw):  # noqa: ANN001
        for tok in ["你好", "，", "这是", "来自", "DeepSeek", "的答案"]:
            yield tok

    OpenAICompatibleProvider.complete = fake_complete  # type: ignore[assignment]
    OpenAICompatibleProvider.stream = fake_stream  # type: ignore[assignment]


async def test_llm() -> None:
    os.environ["RAG_DEFAULT_LLM_PROVIDER"] = "deepseek"
    os.environ["RAG_DEEPSEEK_API_KEY"] = "sk-test"
    from app.services.providers.factory import build_provider, get_llm
    from app.services.providers.openai_compatible import OpenAICompatibleProvider

    _patch_llm()
    inst = build_provider("llm")
    assert isinstance(inst, OpenAICompatibleProvider), f"unexpected: {type(inst)}"
    assert inst.base_url == "https://api.deepseek.com", inst.base_url
    assert inst.model == "deepseek-v4-flash", inst.model

    out = await inst.complete("sys", "user")
    assert '"0": 0.9' in out, out

    tokens = []
    async for t in inst.stream("sys", "user"):
        tokens.append(t)
    assert "".join(tokens) == "你好，这是来自DeepSeek的答案", tokens

    # get_llm() should resolve to the same deepseek provider.
    assert isinstance(get_llm(), OpenAICompatibleProvider)
    print("LLM_OK base_url=%s model=%s" % (inst.base_url, inst.model))


async def test_rerank() -> None:
    os.environ["RAG_RERANK_PROVIDER"] = "deepseek"
    os.environ["RAG_DEEPSEEK_API_KEY"] = "sk-test"
    from app.services.providers.deepseek import DeepSeekReranker, get_reranker

    _patch_llm()  # simulate DeepSeek returning a JSON score map
    rk = get_reranker()
    assert isinstance(rk, DeepSeekReranker), f"expected DeepSeekReranker, got {type(rk)}"

    items = [
        {"chunk_id": "cA", "snippet": "alpha passage"},
        {"chunk_id": "cB", "snippet": "beta passage"},
        {"chunk_id": "cC", "snippet": "gamma passage"},
    ]
    scores = await rk.rerank("test query", items)
    assert scores == {"cA": 0.9, "cB": 0.1, "cC": 0.5}, scores
    # Highest score (cA) must outrank the rest.
    ordered = sorted(scores, key=lambda k: scores[k], reverse=True)
    assert ordered[0] == "cA", ordered
    print("RERANK_OK scores=%s" % scores)

    # Graceful degradation: a failing completion must yield {} (-> RRF fallback).
    from app.services.providers.openai_compatible import OpenAICompatibleProvider

    async def boom(self, system, user, **kw):  # noqa: ANN001
        raise RuntimeError("simulated network error")

    OpenAICompatibleProvider.complete = boom  # type: ignore[assignment]
    assert await rk.rerank("q", items) == {}, "should degrade to {} on error"

    # Robustness: garbage output must yield {}.
    async def garbage(self, system, user, **kw):  # noqa: ANN001
        return "I cannot do that."

    OpenAICompatibleProvider.complete = garbage  # type: ignore[assignment]
    assert await rk.rerank("q", items) == {}, "should degrade on unparsable output"
    print("RERANK_FALLBACK_OK")


async def test_disabled() -> None:
    os.environ["RAG_RERANK_PROVIDER"] = "none"
    os.environ["RAG_DEEPSEEK_API_KEY"] = ""
    from app.services.providers.deepseek import get_reranker

    assert get_reranker() is None, "rerank must be disabled by default"
    print("DISABLED_OK reranker=None")


if __name__ == "__main__":
    if MODE == "llm":
        asyncio.run(test_llm())
    elif MODE == "rerank":
        asyncio.run(test_rerank())
    elif MODE == "disabled":
        asyncio.run(test_disabled())
    else:
        print(f"unknown TEST_MODE={MODE}")
        sys.exit(1)
    print("ALL_DEEPSEEK_WIRING_OK")
