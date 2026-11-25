"""Pydantic schemas for LUMO Phase 14: Personal Intelligence & Knowledge Workspace."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceTagSchema(BaseModel):
    id: int
    name: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceTagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class WorkspaceCollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(None, max_length=1000)
    parent_id: str | None = None


class WorkspaceCollectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, max_length=1000)
    parent_id: str | None = None


class WorkspaceCollectionResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    parent_id: str | None = None
    item_count: int = 0
    note_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field("", max_length=500_000)
    summary: str | None = Field(None, max_length=2000)
    source_type: str = Field("bookmark", max_length=48)
    source_url: str | None = Field(None, max_length=2048)
    source_ref_id: str | None = Field(None, max_length=64)
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceItemUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    content: str | None = Field(None, max_length=500_000)
    summary: str | None = Field(None, max_length=2000)
    collection_id: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class WorkspaceItemResponse(BaseModel):
    id: str
    title: str
    content: str
    summary: str | None = None
    source_type: str
    source_url: str | None = None
    source_ref_id: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    content_hash: str
    collection_id: str | None = None
    collection_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    annotation_count: int = 0
    is_duplicate: bool = False
    last_viewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceItemListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[WorkspaceItemResponse] = Field(default_factory=list)


class WorkspaceUrlImportRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class WorkspaceNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field("", max_length=200_000)
    collection_id: str | None = None
    linked_item_id: str | None = None
    linked_entity_id: str | None = None
    linked_research_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class WorkspaceNoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    content: str | None = Field(None, max_length=200_000)
    collection_id: str | None = None
    linked_item_id: str | None = None
    linked_entity_id: str | None = None
    linked_research_id: str | None = None
    tags: list[str] | None = None


class WorkspaceNoteResponse(BaseModel):
    id: str
    title: str
    content: str
    collection_id: str | None = None
    linked_item_id: str | None = None
    linked_entity_id: str | None = None
    linked_research_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspaceAnnotationCreate(BaseModel):
    selected_text: str = Field(..., min_length=1, max_length=10_000)
    comment: str = Field("", max_length=5_000)
    start_offset: int | None = Field(None, ge=0)
    end_offset: int | None = Field(None, ge=0)
    linked_note_id: str | None = None


class WorkspaceAnnotationUpdate(BaseModel):
    comment: str | None = Field(None, max_length=5_000)
    linked_note_id: str | None = None


class WorkspaceAnnotationResponse(BaseModel):
    id: str
    item_id: str
    selected_text: str
    comment: str
    start_offset: int | None = None
    end_offset: int | None = None
    linked_note_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceSearchRequest(BaseModel):
    query: str = Field("", max_length=400)
    mode: str = Field("hybrid", pattern="^(keyword|semantic|hybrid)$")
    collection_id: str | None = None
    source_type: str | None = None
    tag: str | None = None
    include_notes: bool = True
    include_annotations: bool = True
    limit: int = Field(20, ge=1, le=100)


class WorkspaceSearchHit(BaseModel):
    kind: str  # "item", "note", "annotation"
    id: str
    title: str
    snippet: str
    score: float
    source_type: str | None = None
    source_url: str | None = None
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class WorkspaceSearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    hits: list[WorkspaceSearchHit] = Field(default_factory=list)


class WorkspaceAskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    collection_id: str | None = None
    provider: str | None = None
    max_sources: int = Field(6, ge=1, le=12)


class WorkspaceCitation(BaseModel):
    key: str
    kind: str
    id: str
    title: str
    snippet: str
    source_url: str | None = None


class WorkspaceAskResponse(BaseModel):
    question: str
    answer: str
    status: str  # "completed", "insufficient_evidence", "provider_unavailable"
    provider: str | None = None
    citations: list[WorkspaceCitation] = Field(default_factory=list)


class WorkspaceStatsResponse(BaseModel):
    total_items: int
    total_collections: int
    total_notes: int
    total_tags: int
    total_annotations: int
    items_by_type: dict[str, int] = Field(default_factory=dict)


class WorkspaceDashboardResponse(BaseModel):
    stats: WorkspaceStatsResponse
    recent_items: list[WorkspaceItemResponse] = Field(default_factory=list)
    recently_viewed: list[WorkspaceItemResponse] = Field(default_factory=list)
    collections: list[WorkspaceCollectionResponse] = Field(default_factory=list)
    recent_notes: list[WorkspaceNoteResponse] = Field(default_factory=list)
    tags: list[WorkspaceTagSchema] = Field(default_factory=list)


class WorkspaceConnectionsResponse(BaseModel):
    item_id: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    related_items: list[WorkspaceItemResponse] = Field(default_factory=list)
    linked_notes: list[WorkspaceNoteResponse] = Field(default_factory=list)
