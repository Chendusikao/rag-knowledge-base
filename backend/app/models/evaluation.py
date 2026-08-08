"""EvaluationCase, EvaluationRun, MetricResult (RAG evaluation panel)."""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import EvalType, PKMixin, TimestampMixin


class EvaluationCase(Base, PKMixin, TimestampMixin):
    """A single evaluation question with gold answer + gold chunks.

    PLAN 5: 中文 60% / 英文 40%; types include fact, multihop, table, keyword,
    unanswerable. 20 calibration + 80 held-out.
    """

    __tablename__ = "evaluation_cases"

    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    gold_chunks: Mapped[list] = mapped_column(JSON, default=list)
    case_type: Mapped[str] = mapped_column(String(16), default=EvalType.FACT)
    language: Mapped[str] = mapped_column(String(8), default="zh")  # zh | en
    is_calibration: Mapped[bool] = mapped_column(default=False)


class EvaluationRun(Base, PKMixin, TimestampMixin):
    __tablename__ = "evaluation_runs"

    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="balanced")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|done|failed
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    # Aggregate metrics: mrr@10, recall@5/10, hit@5/10, ndcg@10, faithfulness, etc.
    metrics_summary: Mapped[dict] = mapped_column(JSON, default=dict)

    results: Mapped[list["MetricResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class MetricResult(Base, PKMixin, TimestampMixin):
    __tablename__ = "metric_results"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(default=0.0)
    passed: Mapped[bool] = mapped_column(default=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped["EvaluationRun"] = relationship(back_populates="results")
