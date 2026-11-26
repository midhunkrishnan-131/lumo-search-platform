"""Pydantic schemas for LUMO Phase 30: Intelligence Studio."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StudioProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    subtitle: str | None = Field(default=None, max_length=500)
    description: str = Field(default="")
    document_type: str = Field(default="research_report", max_length=64)
    template_id: str | None = None


class StudioProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    subtitle: str | None = None
    description: str | None = None
    status: str | None = Field(default=None, max_length=32)
    executive_summary: str | None = None
    sections: list[dict[str, Any]] | None = None
    sources: list[dict[str, Any]] | None = None
    charts: list[dict[str, Any]] | None = None
    conclusion: str | None = None
    save_version: bool = True
    change_summary: str = Field(default="Updated document", max_length=300)


class StudioSourceImportRequest(BaseModel):
    source_type: str = Field(..., max_length=48)  # knowledge_item | workflow | research_session | data_analysis | manual
    source_id: str | None = None
    title: str | None = None
    url: str | None = None
    content: str | None = None
    csv_content: str | None = None


class StudioAIAssistRequest(BaseModel):
    action: str = Field(..., max_length=64)
    section_id: str | None = None
    input_text: str = Field(default="", max_length=8000)
    provider: str = Field(default="auto", max_length=64)
    model_name: str | None = Field(default=None, max_length=128)


class StudioSaveKnowledgeRequest(BaseModel):
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)
