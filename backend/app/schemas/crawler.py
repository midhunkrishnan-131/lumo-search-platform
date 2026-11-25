"""Pydantic schemas for crawler API requests and responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateCrawlSessionRequest(BaseModel):
    seed_urls: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of initial seed URLs to begin crawling.",
    )
    name: str | None = Field(default=None, max_length=255, description="Optional name for the crawl session.")
    max_depth: int = Field(default=2, ge=0, le=5, description="Maximum crawl recursion depth (0 to 5).")
    max_pages: int = Field(default=100, ge=1, le=500, description="Maximum total pages to crawl (1 to 500).")
    crawl_delay: float = Field(default=1.0, ge=0.0, le=30.0, description="Politeness delay between requests in seconds.")


class CrawlUrlSummary(BaseModel):
    id: int
    url: str
    normalized_url: str
    depth: int
    is_seed: bool
    status: Literal["queued", "in_progress", "fetched", "failed", "skipped"]
    http_status: int | None = None
    title: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    error_message: str | None = None
    parent_url: str | None = None
    discovered_at: datetime
    fetched_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CrawlSessionResponse(BaseModel):
    id: str
    name: str | None = None
    status: Literal["pending", "running", "completed", "stopped", "failed"]
    max_depth: int
    max_pages: int
    crawl_delay: float
    pages_crawled: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    seeds_count: int = 0
    queued_count: int = 0
    fetched_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CrawlSessionListResponse(BaseModel):
    total: int
    sessions: list[CrawlSessionResponse]


class CrawlUrlListResponse(BaseModel):
    session_id: str
    total: int
    urls: list[CrawlUrlSummary]
