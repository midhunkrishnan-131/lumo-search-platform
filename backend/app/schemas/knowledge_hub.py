"""Pydantic schemas for LUMO Phase 28: Personal Knowledge Hub & Persistent Intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeCollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    icon: str = Field(default="folder", max_length=32)
    tags: list[str] = Field(default_factory=list)


class KnowledgeCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None


class KnowledgeItemSaveRequest(BaseModel):
    item_type: str = Field(default="SOURCE", max_length=48)
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    content: str = Field(default="")
    source_url: str | None = None
    source_ref_id: str | None = Field(default=None, max_length=64)
    collection_id: str | None = None
    new_collection_name: str | None = Field(default=None, max_length=160)
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class KnowledgeItemMoveRequest(BaseModel):
    collection_id: str | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    item_type: str | None = None
    collection_id: str | None = None
    tag: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(default=30, ge=1, le=100)


class KnowledgeNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(default="")
    collection_id: str | None = None
    linked_item_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class KnowledgeNoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = None
    collection_id: str | None = None
    tags: list[str] | None = None


class KnowledgeTagRenameRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=64)


class KnowledgeRelationshipCreate(BaseModel):
    source_item_id: str
    target_item_id: str
    relationship_type: str = Field(default="RELATES_TO", max_length=64)
    evidence: str = Field(default="", max_length=1000)


class KnowledgeContextRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    collection_id: str | None = None
    item_ids: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=6000, ge=200, le=12000)


class KnowledgeImportRequest(BaseModel):
    collections: list[dict[str, Any]] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
