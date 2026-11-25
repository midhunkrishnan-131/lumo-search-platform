"""FastAPI routes for LUMO Phase 23: Intelligence API & Developer Platform."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.developer.service import API_PERMISSIONS, DeveloperPlatformService
from app.schemas.developer import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    ApiUsageSummaryResponse,
)

router = APIRouter(prefix="/developer", tags=["developer-platform"])


@router.get("/info")
def get_developer_platform_info(request: Request) -> dict[str, Any]:
    """Return API platform version, namespaces, permission catalog, and OpenAPI links."""
    cfg = request.app.state.settings
    return {
        "platform": "LUMO Intelligence API",
        "api_version": "v1",
        "app_version": cfg.app_version,
        "auth_headers": ["X-API-Key", "Authorization: Bearer lumo_pk_<token>"],
        "namespaces": [
            "/api/v1/search",
            "/api/v1/ai",
            "/api/v1/research",
            "/api/v1/documents",
            "/api/v1/intelligence",
            "/api/v1/graph",
            "/api/v1/guardian",
            "/api/v1/workspace",
            "/api/v1/integrations",
            "/api/v1/automations",
            "/api/v1/dashboard",
            "/api/v1/ops",
            "/api/v1/developer",
        ],
        "permissions": API_PERMISSIONS,
        "openapi_url": None if cfg.is_production else "/openapi.json",
        "docs_url": None if cfg.is_production else "/docs",
    }


@router.get("/keys", response_model=list[ApiKeyResponse])
def list_api_keys(db: Session = Depends(get_db)):
    return DeveloperPlatformService(db).list_keys()


@router.post("/keys", response_model=ApiKeyCreatedResponse, status_code=201)
def create_api_key(payload: ApiKeyCreateRequest, db: Session = Depends(get_db)):
    try:
        row, raw_key = DeveloperPlatformService(db).create_key(payload)
        return ApiKeyCreatedResponse(key=ApiKeyResponse.model_validate(row), raw_key=raw_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/keys/{key_id}/rotate", response_model=ApiKeyCreatedResponse)
def rotate_api_key(key_id: str, db: Session = Depends(get_db)):
    try:
        row, raw_key = DeveloperPlatformService(db).rotate_key(key_id)
        return ApiKeyCreatedResponse(key=ApiKeyResponse.model_validate(row), raw_key=raw_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/keys/{key_id}/revoke", response_model=ApiKeyResponse)
def revoke_api_key(key_id: str, db: Session = Depends(get_db)):
    try:
        return DeveloperPlatformService(db).revoke_key(key_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/keys/{key_id}")
def delete_api_key(key_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not DeveloperPlatformService(db).delete_key(key_id):
        raise HTTPException(status_code=404, detail="API key not found.")
    return {"deleted": True}


@router.get("/usage", response_model=ApiUsageSummaryResponse)
def get_api_usage(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db)):
    return DeveloperPlatformService(db).get_usage_summary(limit=limit)
