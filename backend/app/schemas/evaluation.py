"""Pydantic schemas for LUMO Phase 25: Intelligence Testing, Benchmarking & Evaluation Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvaluationDatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: str = Field(..., min_length=1, max_length=64)
    version: str = Field(default="1.0", max_length=32)
    cases: list[dict[str, Any]] = Field(..., min_length=1, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class EvaluationDatasetResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    version: str
    format_type: str
    case_count: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EvaluationDatasetDetailResponse(EvaluationDatasetResponse):
    cases_json: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationBenchmarkCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: str = Field(..., min_length=1, max_length=64)
    version: str = Field(default="1.0", max_length=32)
    dataset_id: str | None = None
    target_module: str = Field(..., min_length=1, max_length=64)
    config_json: dict[str, Any] = Field(default_factory=dict)


class EvaluationBenchmarkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    dataset_id: str | None = None
    target_module: str | None = None
    config_json: dict[str, Any] | None = None


class EvaluationBenchmarkResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    version: str
    dataset_id: str | None = None
    target_module: str
    config_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EvaluationRunRequest(BaseModel):
    k: int = Field(default=5, ge=1, le=50)
    provider: str = Field(default="auto", max_length=32)
    model_name: str | None = Field(default=None, max_length=128)
    max_cases: int = Field(default=50, ge=1, le=200)
    use_llm_judge: bool = False
    judge_provider: str | None = Field(default=None, max_length=32)
    judge_model: str | None = Field(default=None, max_length=128)


class EvaluationRunResponse(BaseModel):
    id: str
    benchmark_id: str
    dataset_version: str
    target_module: str
    model_name: str | None = None
    provider_name: str | None = None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class EvaluationRunDetailResponse(EvaluationRunResponse):
    results_json: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationReviewCreate(BaseModel):
    case_id: str | None = Field(default=None, max_length=64)
    score: int = Field(..., ge=1, le=5)
    reviewer_notes: str = Field(default="", max_length=2000)
    status: str = Field(default="approved", pattern="^(approved|flagged)$")


class EvaluationReviewResponse(BaseModel):
    id: str
    run_id: str
    case_id: str | None = None
    score: int
    reviewer_notes: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
