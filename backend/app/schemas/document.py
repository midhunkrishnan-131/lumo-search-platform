"""Pydantic schemas for Document representations and API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HeadingItem(BaseModel):
    tag: str
    level: int
    text: str


class DocumentMetadataResponse(BaseModel):
    id: str
    url_id: int | None = None
    session_id: str | None = None
    url: str
    canonical_url: str | None = None
    title: str | None = None
    description: str | None = None
    language: str | None = None
    author: str | None = None
    published_date: str | None = None
    modified_date: str | None = None
    content_type: str = "text/html"
    content_hash: str
    is_duplicate: bool
    primary_document_id: str | None = None
    extraction_status: str
    word_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(DocumentMetadataResponse):
    main_content: str
    headings: list[HeadingItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    documents: list[DocumentMetadataResponse]


class ProcessDocumentRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL.")
    html: str = Field(..., description="Raw HTML content to process.")
    session_id: str | None = Field(default=None, description="Optional crawl session ID to associate with.")
