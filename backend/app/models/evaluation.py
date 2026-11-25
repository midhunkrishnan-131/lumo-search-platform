"""SQLAlchemy models for LUMO Phase 25: Intelligence Testing, Benchmarking & Evaluation Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationDataset(Base):
    """Versioned evaluation dataset containing bounded test cases for LUMO modules."""

    __tablename__ = "evaluation_datasets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    category = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False, default="1.0")
    format_type = Column(String(24), nullable=False, default="json")
    case_count = Column(Integer, nullable=False, default=0)
    cases_json = Column(JSON, nullable=False, default=list)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    benchmarks = orm_relationship("EvaluationBenchmark", back_populates="dataset")


class EvaluationBenchmark(Base):
    """Registered benchmark configuration targeting a LUMO intelligence module."""

    __tablename__ = "evaluation_benchmarks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    category = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False, default="1.0")
    dataset_id = Column(
        String(36),
        ForeignKey("evaluation_datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_module = Column(String(64), nullable=False, index=True)
    config_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="idle", index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    dataset = orm_relationship("EvaluationDataset", back_populates="benchmarks")
    runs = orm_relationship("EvaluationRun", back_populates="benchmark", cascade="all, delete-orphan")


class EvaluationRun(Base):
    """Executed benchmark run storing aggregate metrics, latency stats, and per-case results."""

    __tablename__ = "evaluation_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    benchmark_id = Column(
        String(36),
        ForeignKey("evaluation_benchmarks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version = Column(String(32), nullable=False, default="1.0")
    target_module = Column(String(64), nullable=False, index=True)
    model_name = Column(String(128), nullable=True)
    provider_name = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="running", index=True)
    total_cases = Column(Integer, nullable=False, default=0)
    passed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    metrics_json = Column(JSON, nullable=False, default=dict)
    results_json = Column(JSON, nullable=False, default=list)
    config_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    benchmark = orm_relationship("EvaluationBenchmark", back_populates="runs")
    reviews = orm_relationship("EvaluationReview", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_eval_runs_bench_started", "benchmark_id", "started_at"),
    )


class EvaluationReview(Base):
    """Human review score and notes attached to an evaluation run or specific case."""

    __tablename__ = "evaluation_reviews"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id = Column(String(64), nullable=True)
    score = Column(Integer, nullable=False)
    reviewer_notes = Column(Text, nullable=False, default="")
    status = Column(String(32), nullable=False, default="approved")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    run = orm_relationship("EvaluationRun", back_populates="reviews")
