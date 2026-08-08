"""Dify Agent provider (PLAN 3 "Dify Agent Provider").

The Dify Agent receives THIS system's ``context_bundle`` (already retrieved and
ranked locally) and returns a unified answer structure. Crucially, Dify MUST NOT
bypass local citation verification (PLAN 3): we still bind/verify citations
against our own chunks after Dify returns its answer.

This is a STUB with the request/response contract sketched. The exact Dify Agent
API path/body should be confirmed against the Dify version in use; the
``answer`` method maps the response into our ``AnswerResult``.
"""
from __future__ import annotations

import httpx

from app.services.providers.base import AnswerResult, AgentProvider
from app.services.providers.secret_store import get_secret


class DifyAgentProvider(AgentProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        credential_ref: str | None = None,
        timeout: float = 60.0,
        user_key: str = "rag-local-user",
    ):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.credential_ref = credential_ref
        self.timeout = timeout
        self.user_key = user_key

    @property
    def api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        return get_secret(self.credential_ref)

    async def answer(self, context_bundle: dict, query: str, *, system=None) -> AnswerResult:
        if not self.base_url or not self.api_key:
            raise RuntimeError("Dify provider requires base_url + api_key (via credential_ref)")
        # Dify Agent API (contract sketch; verify against your Dify version).
        payload = {
            "inputs": {
                "context_bundle": context_bundle,  # our local retrieval result
                "query": query,
                "system": system,
            },
            "query": query,
            "user": self.user_key,
            "response_mode": "blocking",
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat-messages", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        # Map Dify response -> our AnswerResult (field names TBD per Dify version).
        answer = data.get("answer", "")
        # Dify does not own our chunks; we keep local citations from context_bundle.
        citations = context_bundle.get("citations", [])
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=0.8 if citations else 0.2,
            insufficient_evidence=not citations,
        )
