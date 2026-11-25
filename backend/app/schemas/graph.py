"""Pydantic schemas for LUMO Phase 11: Knowledge Graph & Entity Intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EntityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field("Concept", max_length=64)
    description: str | None = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class EntityResponse(EntityBase):
    id: str
    normalized_name: str
    extraction_method: str
    created_at: datetime
    updated_at: datetime
    mention_count: int = 0
    degree: int = 0

    model_config = {"from_attributes": True}


class EntityAliasResponse(BaseModel):
    id: int
    entity_id: str
    alias: str
    normalized_alias: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityDocumentResponse(BaseModel):
    id: int
    entity_id: str
    document_id: str
    mention_count: int
    confidence: float
    first_snippet: str | None = None
    document_title: str | None = None
    document_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RelationshipEvidenceResponse(BaseModel):
    id: int
    relationship_id: str
    document_id: str
    snippet: str
    document_title: str | None = None
    document_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RelationshipResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    source_name: str | None = None
    target_name: str | None = None
    relationship_type: str
    confidence: float
    extraction_method: str
    weight: float
    created_at: datetime
    evidence: list[RelationshipEvidenceResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EntityDetailResponse(EntityResponse):
    aliases: list[str] = Field(default_factory=list)
    relationships: list[RelationshipResponse] = Field(default_factory=list)
    documents: list[EntityDocumentResponse] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    description: str | None = None
    degree: int = 0
    confidence: float = 1.0
    x: float | None = None
    y: float | None = None
    sources_count: int = 0


class GraphEdge(BaseModel):
    id: str
    from_: str = Field(..., alias="from")
    to: str
    label: str
    weight: float = 1.0
    confidence: float = 1.0
    evidence_count: int = 0
    first_snippet: str | None = None

    model_config = {"populate_by_name": True}


class GraphOverviewResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    truncated: bool = False


class EntityConnectionsResponse(BaseModel):
    entity: EntityResponse
    depth: int
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class EntitySearchResponse(BaseModel):
    query: str
    total: int
    items: list[EntityResponse] = Field(default_factory=list)


class GraphStatsResponse(BaseModel):
    total_entities: int
    entities_by_type: dict[str, int] = Field(default_factory=dict)
    total_relationships: int
    relationships_by_type: dict[str, int] = Field(default_factory=dict)
    total_documents_represented: int
    graph_density: float = 0.0
    top_connected_entities: list[dict[str, Any]] = Field(default_factory=list)


class ReprocessGraphRequest(BaseModel):
    document_ids: list[str] | None = None
    batch_size: int = Field(50, ge=1, le=500)
    use_ai: bool = False


class ReprocessGraphResponse(BaseModel):
    status: str
    documents_processed: int
    entities_extracted: int
    relationships_extracted: int
    duration_ms: float
