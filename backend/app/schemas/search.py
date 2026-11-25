"""Pydantic schemas for Search queries and responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchResultItem(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    category: str = "Indexed"
    published_at: str = ""
    description: str = ""
    snippet: str = ""
    score: float = 0.0
    canonical_url: str | None = None
    language: str | None = None
    classic_rank: int | None = None
    semantic_rank: int | None = None
    sources: list[str] = Field(default_factory=list)
    hybrid_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    source: str = "api"
    query: str
    mode: str = "classic"
    total: int
    page: int
    per_page: int
    total_pages: int
    results: list[SearchResultItem] = Field(default_factory=list)
    degraded: bool = False
    execution_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
