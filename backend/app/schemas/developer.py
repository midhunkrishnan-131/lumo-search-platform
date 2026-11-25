"""Pydantic schemas for LUMO Phase 23: Intelligence API & Developer Platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    permissions: list[str] = Field(default_factory=lambda: ["search:read"])
    rate_limit_rpm: int = Field(default=60, ge=5, le=1000)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    permissions_json: list[str] = Field(default_factory=list)
    rate_limit_rpm: int
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(BaseModel):
    key: ApiKeyResponse
    raw_key: str
    warning: str = "Store this API key securely now. It will not be shown again."


class ApiUsageItemResponse(BaseModel):
    id: str
    key_prefix: str | None = None
    endpoint: str
    method: str
    status_code: int
    duration_ms: int
    rate_limited: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiUsageSummaryResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    rate_limited_requests: int
    by_endpoint: list[dict[str, Any]] = Field(default_factory=list)
    recent: list[ApiUsageItemResponse] = Field(default_factory=list)
