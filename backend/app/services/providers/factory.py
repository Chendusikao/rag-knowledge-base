"""Provider factory + small in-memory registry.

Builds provider instances from ``ProviderProfile`` rows (and config defaults).
Mock is the default so the system runs with no secrets / GPU.
"""
from __future__ import annotations

from app.core.config import settings
from app.models.provider import ProviderProfile
from app.services.providers.base import (
    AgentProvider,
    EmbeddingProvider,
    LLMProvider,
    VisionProvider,
)
from app.services.providers.dify import DifyAgentProvider
from app.services.providers.local_embedding import LocalEmbedding
from app.services.providers.lexical_embedding import LocalLexicalEmbedding
from app.services.providers.mock import MockAgent, MockEmbedding, MockLLM, MockVision
from app.services.providers.openai_compatible import (
    OpenAICompatibleAgent,
    OpenAICompatibleProvider,
)

_REGISTRY: dict[tuple[str, str], object] = {}


def build_provider(role: str, profile: ProviderProfile | None = None) -> object:
    """Build a provider for ``role`` (llm|embedding|vision|agent).

    If a persisted ``ProviderProfile`` exists it wins; otherwise fall back to the
    configured default kind (which is ``mock`` by default).
    """
    if profile is not None and profile.enabled:
        kind = profile.kind
        base = profile.base_url
        model = profile.model
        ref = profile.credential_ref
    else:
        kind = {
            "embedding": settings.default_embedding_provider,
            "llm": settings.default_llm_provider,
            "vision": settings.default_vision_provider,
            "agent": settings.default_agent_provider,
        }.get(role, "mock")
        base, model, ref = "", "", None

    key = (role, kind)
    if key in _REGISTRY:
        return _REGISTRY[key]

    if kind == "mock":
        inst: object = {
            "embedding": MockEmbedding(),
            "llm": MockLLM(),
            "vision": MockVision(),
            "agent": MockAgent(),
        }[role]
    elif kind == "local":
        # Real local embeddings (sentence-transformers). Only the embedding role
        # is supported by this provider; other roles fall back to mock.
        if role == "embedding":
            inst = LocalEmbedding(
                model_name=settings.local_embedding_model or "BAAI/bge-small-zh-v1.5",
                model_path=settings.local_embedding_model_path or None,
            )
        else:
            inst = {
                "llm": MockLLM(), "vision": MockVision(), "agent": MockAgent()
            }[role]
    elif kind == "local-lexical":
        # Zero-download, offline, content-derived (lexical) embedding. Use this
        # when model weights cannot be downloaded. Only embedding role is served;
        # other roles fall back to mock.
        if role == "embedding":
            inst = LocalLexicalEmbedding(dim=settings.local_embedding_dim)
        else:
            inst = {
                "llm": MockLLM(), "vision": MockVision(), "agent": MockAgent()
            }[role]
    elif kind == "openai_compatible":
        base_provider = OpenAICompatibleProvider(base_url=base, model=model, credential_ref=ref)
        inst = {
            "embedding": base_provider,
            "llm": base_provider,
            "vision": base_provider,  # many OpenAI-compatible servers expose vision models
            "agent": OpenAICompatibleAgent(base_provider),
        }[role]
    elif kind == "dify":
        inst = DifyAgentProvider(base_url=base, credential_ref=ref)
    elif kind == "deepseek":
        # DeepSeek is an OpenAI-compatible endpoint. Reuse the same provider;
        # the secret resolves from settings (RAG_DEEPSEEK_API_KEY) only.
        base_provider = OpenAICompatibleProvider(
            base_url=base or settings.deepseek_base_url,
            model=model or settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            credential_ref=ref,
        )
        inst = {
            "embedding": base_provider,
            "llm": base_provider,
            "vision": base_provider,
            "agent": OpenAICompatibleAgent(base_provider),
        }[role]
    else:
        raise ValueError(f"Unknown provider kind: {kind}")

    _REGISTRY[key] = inst
    return inst


def get_embedding() -> EmbeddingProvider:
    return build_provider("embedding")  # type: ignore[return-value]


def get_llm() -> LLMProvider:
    return build_provider("llm")  # type: ignore[return-value]


def get_vision() -> VisionProvider:
    return build_provider("vision")  # type: ignore[return-value]


def get_agent() -> AgentProvider:
    return build_provider("agent")  # type: ignore[return-value]
