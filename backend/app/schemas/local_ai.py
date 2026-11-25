"""Pydantic schemas for LUMO Phase 15: Offline AI Intelligence Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LocalAIModelInfo(BaseModel):
    name: str
    size_bytes: int = 0
    size_gb: float = 0.0
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    modified_at: str | None = None


class LocalAIStatusResponse(BaseModel):
    reachable: bool
    enabled: bool
    local_only_mode: bool
    primary_provider: str
    default_model: str
    models_count: int = 0
    setup_instructions: str | None = None


class LocalAIModelsResponse(BaseModel):
    reachable: bool
    default_model: str
    models: list[LocalAIModelInfo] = Field(default_factory=list)


class LocalAITestRequest(BaseModel):
    model: str | None = Field(None, max_length=120)


class LocalAITestResponse(BaseModel):
    success: bool
    model: str
    latency_ms: float
    message: str


class LocalAIConfigUpdate(BaseModel):
    ollama_enabled: bool | None = None
    local_only_mode: bool | None = None
    ollama_model: str | None = Field(None, min_length=1, max_length=120)
    primary_provider: Literal["gemini", "grok", "ollama"] | None = None


class LocalAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=40_000)


class LocalAIChatRequest(BaseModel):
    messages: list[LocalAIChatMessage] = Field(..., min_length=1, max_length=40)
    model: str | None = Field(None, max_length=120)
    use_rag: bool = False
    rag_scope: Literal["web", "workspace", "both"] = "both"
    temperature: float = Field(0.2, ge=0.0, le=1.5)


class LocalAICitation(BaseModel):
    key: str
    title: str
    source_type: str
    source_url: str | None = None
    snippet: str


class LocalAIChatResponse(BaseModel):
    answer: str
    model: str
    provider: str = "ollama"
    local_only: bool = True
    citations: list[LocalAICitation] = Field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


LocalAITaskType = Literal[
    "summarize",
    "qa",
    "research_analysis",
    "extract_info",
    "study_notes",
    "faq",
    "compare",
    "classify",
    "structured",
]


class LocalAITaskRequest(BaseModel):
    task_type: LocalAITaskType
    prompt: str = Field(..., min_length=1, max_length=30_000)
    document_ids: list[str] = Field(default_factory=list, max_length=10)
    workspace_item_ids: list[str] = Field(default_factory=list, max_length=10)
    use_rag: bool = False
    model: str | None = Field(None, max_length=120)
    run_async: bool = False


class LocalAITaskResponse(BaseModel):
    task_id: str
    task_type: LocalAITaskType
    status: Literal["pending", "running", "completed", "cancelled", "failed"]
    model: str
    result: str | None = None
    citations: list[LocalAICitation] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
