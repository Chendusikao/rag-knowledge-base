"""Pydantic schemas for RAG evaluation."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCaseCreate(BaseModel):
    kb_id: str
    question: str
    expected_answer: str = ""
    gold_chunks: list[str] = Field(default_factory=list)
    case_type: str = "fact"  # fact|multihop|table|keyword|unanswerable
    language: str = "zh"     # zh|en
    is_calibration: bool = False


class EvaluationCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    question: str
    expected_answer: str
    gold_chunks: list[str]
    case_type: str
    language: str
    is_calibration: bool
    created_at: datetime


class EvaluationRunCreate(BaseModel):
    kb_id: str
    mode: str = "balanced"
    case_ids: list[str] = Field(default_factory=list)  # empty => all non-calibration


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    mode: str
    status: str
    case_count: int
    metrics_summary: dict
    created_at: datetime
