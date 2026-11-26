"""Pydantic schemas for LUMO Phase 27: Unified Intelligence Workspace & Orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    user_request: str = Field(..., min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=255)
    preferred_intent: str | None = Field(default=None, max_length=64)
    allowed_modules: list[str] | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecuteRequest(BaseModel):
    provider: str = Field(default="auto", max_length=64)
    model_name: str | None = Field(default=None, max_length=128)
    search_mode: str = Field(default="hybrid", max_length=32)
    step_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)


class WorkflowStepResponse(BaseModel):
    id: str
    step_key: str
    module_name: str
    title: str
    depends_on_json: list[str]
    status: str
    output_ref_json: dict[str, Any]
    error_message: str | None
    duration_ms: float | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: str
    owner_id: str
    title: str
    user_request: str
    intent: str
    selected_modules_json: list[str]
    status: str
    progress: float
    cancel_requested: bool
    summary: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowDetailResponse(WorkflowResponse):
    plan_json: dict[str, Any]
    results_json: dict[str, Any]
    sources_json: list[dict[str, Any]]
    disagreements_json: list[dict[str, Any]]
    errors_json: list[dict[str, Any]]
    execution_metadata_json: dict[str, Any]
    steps: list[WorkflowStepResponse] = Field(default_factory=list)
