"""Pydantic schemas for LUMO Phase 22: External Integration Layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IntegrationCatalogItem(BaseModel):
    id: str
    name: str
    category: str
    description: str
    version: str
    capabilities: list[str] = Field(default_factory=list)
    default_permissions: list[str] = Field(default_factory=list)
    config_fields: list[dict[str, Any]] = Field(default_factory=list)


class IntegrationResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    version: str
    enabled: bool
    status: str
    connection_status: str
    permissions_json: list[str] = Field(default_factory=list)
    config_json: dict[str, Any] = Field(default_factory=dict)
    has_secret: bool = False
    sync_frequency_minutes: int
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationConfigureRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] | None = None
    sync_frequency_minutes: int | None = Field(default=None, ge=5, le=10080)
    secret_token: str | None = Field(default=None, max_length=512)
    clear_secret: bool = False


class IntegrationSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=240)
    source_url: str = Field(..., min_length=4, max_length=2048)
    source_type: str = Field(default="feed", max_length=48)
    monitored: bool = True
    sync_frequency_minutes: int = Field(default=60, ge=5, le=10080)
    config_json: dict[str, Any] = Field(default_factory=dict)


class IntegrationSourceResponse(BaseModel):
    id: str
    integration_id: str
    name: str
    source_url: str
    source_type: str
    monitored: bool
    paused: bool
    sync_frequency_minutes: int
    last_synced_at: datetime | None = None
    last_error: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncRunResponse(BaseModel):
    id: str
    integration_id: str
    source_id: str | None = None
    trigger_mode: str
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    duration_ms: int
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class IntegrationImportRecordResponse(BaseModel):
    id: str
    integration_id: str
    source_id: str | None = None
    external_id: str | None = None
    content_hash: str
    title: str
    url: str | None = None
    workspace_item_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IntegrationSyncRequest(BaseModel):
    source_id: str | None = None
    summarize_with_ai: bool = False
    ai_provider: str = "auto"
    max_items: int = Field(default=15, ge=1, le=50)
