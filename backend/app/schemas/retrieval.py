"""Pydantic schemas for LUMO Phase 29: Advanced Retrieval & Indexing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IndexContentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_type: str = Field(default="document", max_length=48)
    source_ref_id: str | None = Field(default=None, max_length=64)
    url: str | None = None
    content_type: str = Field(default="text", max_length=32)
    chunk_size: int = Field(default=500, ge=100, le=4000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    mode: str = Field(default="hybrid", max_length=32)
    limit: int = Field(default=10, ge=1, le=50)
    domain: str | None = None
    language: str | None = None
    content_type: str | None = None
    collection_id: str | None = None
    tag: str | None = None
    include_knowledge_hub: bool = True
    rerank: bool = True
