"""Pydantic schemas for Search and Browsing History."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchHistoryItem(BaseModel):
    id: str
    query: str
    mode: str
    filters: dict[str, Any] = Field(default_factory=dict)
    total_results: int
    session_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchHistoryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SearchHistoryItem]


class RecordBrowseRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL visited.")
    title: str | None = Field(default=None, description="Title of the visited page.")
    document_id: str | None = Field(default=None, description="Optional associated Document ID.")
    session_id: str | None = Field(default=None, description="Client session identifier.")
    dwell_seconds: int = Field(default=0, ge=0, description="Dwell time in seconds.")
    referrer: str | None = Field(default=None, description="HTTP referrer or originating page.")


class BrowsingHistoryItem(BaseModel):
    id: str
    document_id: str | None = None
    url: str
    title: str | None = None
    domain: str | None = None
    session_id: str | None = None
    visited_at: datetime
    dwell_seconds: int = 0
    referrer: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BrowsingHistoryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[BrowsingHistoryItem]


class ClearHistoryResponse(BaseModel):
    success: bool = True
    deleted_count: int
