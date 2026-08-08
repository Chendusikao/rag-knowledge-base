"""Pydantic schemas for ProviderProfile (capability + credential reference)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderProfileCreate(BaseModel):
    role: str  # llm | embedding | vision | agent
    name: str = ""
    kind: str = "mock"  # mock | openai_compatible | dify
    base_url: str = ""
    model: str = ""
    credential_ref: str | None = None
    capabilities: dict = Field(default_factory=dict)
    enabled: bool = True
    notes: str = ""


class ProviderProfileUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    model: str | None = None
    credential_ref: str | None = None
    capabilities: dict | None = None
    enabled: bool | None = None
    notes: str | None = None


class ProviderProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    name: str
    kind: str
    base_url: str
    model: str
    credential_ref: str | None = None
    capabilities: dict
    enabled: bool
    notes: str
    created_at: datetime
    updated_at: datetime


class ProviderTestRequest(BaseModel):
    """Optional inline config to test before persisting (PLAN PUT .../test)."""

    role: str
    kind: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    credential_ref: str | None = None


class ProviderTestResponse(BaseModel):
    ok: bool
    latency_ms: int = 0
    detail: str = ""
    capabilities: dict = Field(default_factory=dict)
