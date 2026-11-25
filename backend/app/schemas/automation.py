"""Pydantic schemas for LUMO Phase 16: Intelligence Automation Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StepType = Literal[
    "search",
    "hybrid_search",
    "semantic_search",
    "ai_summarize",
    "document_analysis",
    "research_agent",
    "workspace_save",
    "collection_assign",
    "tag_assign",
    "report_generate",
    "notification",
    "condition",
    "output_store",
]

TriggerType = Literal["manual", "scheduled", "event"]

SupportedEventName = Literal[
    "document_indexed",
    "workspace_saved",
    "research_completed",
    "collection_updated",
    "page_crawled",
    "entity_detected",
]


class WorkflowStepSchema(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    type: StepType
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    workflow_type: str = Field("custom", max_length=64)
    trigger_type: TriggerType = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepSchema] = Field(..., min_length=1, max_length=20)
    output_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    max_executions_per_day: int = Field(24, ge=1, le=200)
    timeout_seconds: int = Field(120, ge=10, le=600)
    max_retries: int = Field(1, ge=0, le=3)


class AutomationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    workflow_type: str | None = Field(None, max_length=64)
    trigger_type: TriggerType | None = None
    trigger_config: dict[str, Any] | None = None
    steps: list[WorkflowStepSchema] | None = Field(None, min_length=1, max_length=20)
    output_config: dict[str, Any] | None = None
    enabled: bool | None = None
    max_executions_per_day: int | None = Field(None, ge=1, le=200)
    timeout_seconds: int | None = Field(None, ge=10, le=600)
    max_retries: int | None = Field(None, ge=0, le=3)


class AutomationResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    workflow_type: str
    trigger_type: str
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    output_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    max_executions_per_day: int
    timeout_seconds: int
    max_retries: int
    version: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationStepLogResponse(BaseModel):
    id: int
    step_id: str
    step_type: str
    status: str
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: float
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AutomationExecutionResponse(BaseModel):
    id: str
    automation_id: str
    automation_name: str | None = None
    trigger_source: str
    status: str
    current_step_index: int
    total_steps: int
    retry_count: int
    output_summary: str | None = None
    workspace_item_id: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    step_logs: list[AutomationStepLogResponse] = Field(default_factory=list)


class AutomationNotificationResponse(BaseModel):
    id: str
    automation_id: str | None = None
    execution_id: str | None = None
    event_type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AutomationTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    workflow_type: str
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepSchema] = Field(default_factory=list)
