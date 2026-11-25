"""Pydantic schemas for semantic indexing and vector status."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentSemanticStatus(BaseModel):
    document_id: str
    semantic_status: str
    indexed_chunks_count: int
    semantic_indexed_at: datetime | None = None
    semantic_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SemanticIndexStatusResponse(BaseModel):
    total_documents: int
    indexed_documents: int
    pending_documents: int
    failed_documents: int
    total_vectors: int
    embedding_backend: str
    model_name: str
    dimension: int
    is_qdrant_live: bool


class BatchIndexResponse(BaseModel):
    requested: int
    indexed_count: int
    status: str = "completed"
