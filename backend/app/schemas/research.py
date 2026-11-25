"""Pydantic schemas for Autonomous Research Agent sessions, plans, and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchPlan(BaseModel):
    """Decomposed research objectives, subquestions, and target queries."""

    topic: str
    objectives: list[str] = Field(default_factory=list)
    subquestions: list[str] = Field(default_factory=list)
    initial_queries: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)


class ResearchEvidenceItem(BaseModel):
    """A collected piece of evidence mapped to a session source ID."""

    source_id: str = Field(description="Session source key, e.g. S1")
    document_id: str
    title: str
    url: str
    domain: str
    passage: str
    query: str
    iteration: int
    score: float = 0.0


class ResearchFindingItem(BaseModel):
    """An analytical finding extracted during evidence evaluation."""

    kind: str = Field(description="Supported Finding, Contradiction Noted, or Information Gap")
    text: str = Field(description="Analytical insight or gap statement")
    citations: list[str] = Field(default_factory=list, description="Associated source keys e.g. ['S1', 'S2']")


class ResearchCreateRequest(BaseModel):
    """Payload to initiate a research session."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(default="", max_length=500, description="Research topic or question")
    topic: str | None = Field(default=None, max_length=500, description="Alias for query")
    question: str | None = Field(default=None, max_length=500, description="Alias for query")

    max_iterations: int = Field(default=3, ge=1, le=8, description="Maximum research loop iterations")
    max_queries: int = Field(default=12, ge=1, le=30, description="Maximum total search queries")
    max_sources: int = Field(default=30, ge=1, le=50, description="Maximum collected source documents")
    provider: str = Field(default="auto", description="AI provider: auto, gemini, grok, ollama")
    auto_start: bool = Field(default=True, description="Whether to begin research execution immediately")

    @model_validator(mode="after")
    def unify_query(self) -> ResearchCreateRequest:
        if not self.query:
            self.query = self.topic or self.question or ""
        self.query = self.query.strip()
        return self


class ResearchSessionResponse(BaseModel):
    """Progress and metadata summary for a research session."""

    id: str
    topic: str
    status: str
    current_iteration: int
    max_iterations: int
    max_queries: int
    max_sources: int
    provider: str
    plan: dict[str, Any] = Field(default_factory=dict)
    queries_count: int = 0
    sources_count: int = 0
    findings_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ResearchSessionDetailResponse(ResearchSessionResponse):
    """Detailed research session containing full audit trail, sources, and report."""

    queries_executed: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    report_markdown: str = ""


class ResearchReportResponse(BaseModel):
    """Completed research report with verified source citations."""

    session_id: str
    topic: str
    status: str
    report_markdown: str
    plan: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    completed_at: datetime | None = None


class ResearchSessionListResponse(BaseModel):
    """Paginated list of research sessions."""

    items: list[ResearchSessionResponse]
    total: int
    limit: int
    offset: int


