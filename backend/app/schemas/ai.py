"""Pydantic schemas for LUMO AI Search, RAG pipeline, citations, and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CitationItem(BaseModel):
    """A verified source citation linked from an AI answer."""

    citation_id: str = Field(description="Citation badge token, e.g. [S1]")
    source_id: str = Field(description="Clean source key, e.g. S1")
    document_id: str = Field(description="LUMO internal document UUID")
    title: str = Field(description="Document title")
    url: str = Field(description="Canonical original URL")
    domain: str = Field(description="Registered domain")
    snippet: str = Field(description="Contextual snippet containing evidence")


class SourceItem(BaseModel):
    """A retrieved source document supplied in the context."""

    source_id: str = Field(description="Clean source key, e.g. S1")
    document_id: str = Field(description="LUMO internal document UUID")
    title: str = Field(description="Document title")
    url: str = Field(description="Canonical original URL")
    domain: str = Field(description="Registered domain")
    snippet: str = Field(description="Relevant snippet")
    score: float = Field(default=0.0, description="Retrieval score")
    retrieval_sources: list[str] = Field(default_factory=list, description="Engines that retrieved this source: ['classic'], ['semantic'], or both")


class AISearchRequest(BaseModel):
    """Payload for POST /api/v1/search/ai."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(default="", max_length=500, description="User question or research topic")
    question: str | None = Field(default=None, max_length=500, description="Alias for query")
    page_size: int = Field(default=8, ge=1, le=25, description="Number of candidate documents to retrieve")
    max_sources: int | None = Field(default=None, ge=1, le=25, description="Alias for page_size")
    max_steps: int | None = Field(default=None, description="Optional step limit (for research interface compatibility)")
    provider: str = Field(default="auto", description="Target provider: auto, gemini, grok, ollama")
    domain: str | None = Field(default=None, description="Optional domain filter")
    language: str | None = Field(default=None, description="Optional language filter")
    privacy: bool = Field(default=False, description="When True, disables search history recording")
    session_id: str | None = Field(default=None, description="Client session ID")

    @model_validator(mode="after")
    def unify_query_and_sources(self) -> AISearchRequest:
        if not self.query and self.question:
            self.query = self.question
        if self.max_sources is not None:
            self.page_size = self.max_sources
        self.query = self.query.strip()
        return self


class AISearchResponse(BaseModel):
    """Grounded AI Search response with citations and metadata."""

    query: str = Field(description="Original user question")
    answer: str = Field(description="Grounded AI response with [S1] citation references")
    report: str = Field(description="Full text report for research interface compatibility")
    citations: list[CitationItem] = Field(default_factory=list, description="Verified citations appearing in the answer")
    sources: list[SourceItem] = Field(default_factory=list, description="All evidence sources available in context")
    provider: str = Field(description="AI provider that generated the response")
    model: str = Field(description="Specific model identifier used")
    fallback_used: bool = Field(default=False, description="Whether fallback provider was engaged")
    status: str = Field(default="success", description="Status: success, insufficient_evidence, degraded, error")
    execution_metadata: dict[str, Any] = Field(default_factory=dict, description="Diagnostics, timings, token counts")
