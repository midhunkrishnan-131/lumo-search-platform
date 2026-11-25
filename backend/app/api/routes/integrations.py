"""FastAPI routes for LUMO Phase 22: External Integration Layer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.integrations.manager import IntegrationManager
from app.intelligence.security import redact_secrets
from app.models.integrations import IntegrationImportRecord, IntegrationSyncRun
from app.schemas.integrations import (
    IntegrationCatalogItem,
    IntegrationConfigureRequest,
    IntegrationImportRecordResponse,
    IntegrationResponse,
    IntegrationSourceCreate,
    IntegrationSourceResponse,
    IntegrationSyncRequest,
    SyncRunResponse,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(db: Session = Depends(get_db)):
    return IntegrationManager(db).list_integrations()


@router.get("/available", response_model=list[IntegrationCatalogItem])
def list_available_integrations(db: Session = Depends(get_db)):
    return IntegrationManager(db).list_available_catalog()


@router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(integration_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).get_integration(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/enable", response_model=IntegrationResponse)
def enable_integration(integration_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).enable_integration(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/disable", response_model=IntegrationResponse)
def disable_integration(integration_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).disable_integration(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/configure", response_model=IntegrationResponse)
def configure_integration(
    integration_id: str, payload: IntegrationConfigureRequest, db: Session = Depends(get_db)
):
    try:
        return IntegrationManager(db).configure_integration(integration_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc


@router.post("/{integration_id}/test")
def test_integration(integration_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return IntegrationManager(db).test_connection(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/sync", response_model=SyncRunResponse)
def sync_integration(
    integration_id: str,
    payload: IntegrationSyncRequest | None = None,
    db: Session = Depends(get_db),
):
    req = payload or IntegrationSyncRequest()
    try:
        return IntegrationManager(db).sync_integration(
            integration_id=integration_id,
            source_id=req.source_id,
            summarize_with_ai=req.summarize_with_ai,
            ai_provider=req.ai_provider,
            max_items=req.max_items,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc


@router.get("/{integration_id}/status")
def get_integration_status(integration_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        rec = IntegrationManager(db).get_integration(integration_id)
        sources_count = len(IntegrationManager(db).list_sources(integration_id))
        return {
            "id": rec.id,
            "name": rec.name,
            "enabled": rec.enabled,
            "status": rec.status,
            "connection_status": rec.connection_status,
            "sources_count": sources_count,
            "last_sync_at": rec.last_sync_at,
            "last_sync_error": rec.last_sync_error,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{integration_id}/history", response_model=list[SyncRunResponse])
def get_integration_history(
    integration_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        IntegrationManager(db).get_integration(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return (
        db.query(IntegrationSyncRun)
        .filter(IntegrationSyncRun.integration_id == integration_id)
        .order_by(IntegrationSyncRun.started_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{integration_id}/records", response_model=list[IntegrationImportRecordResponse])
def get_integration_records(
    integration_id: str,
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return (
        db.query(IntegrationImportRecord)
        .filter(IntegrationImportRecord.integration_id == integration_id)
        .order_by(IntegrationImportRecord.created_at.desc())
        .limit(limit)
        .all()
    )


@router.delete("/{integration_id}")
def reset_or_remove_integration(integration_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    mgr = IntegrationManager(db)
    try:
        rec = mgr.get_integration(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.delete(rec)
    db.commit()
    return {"deleted": True}


# --- Monitored Sources ---


@router.get("/{integration_id}/sources", response_model=list[IntegrationSourceResponse])
def list_sources(integration_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).list_sources(integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{integration_id}/sources", response_model=IntegrationSourceResponse, status_code=201)
def add_source(integration_id: str, payload: IntegrationSourceCreate, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).add_source(integration_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc


@router.post("/sources/{source_id}/pause", response_model=IntegrationSourceResponse)
def pause_source(source_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).set_source_paused(source_id, True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sources/{source_id}/resume", response_model=IntegrationSourceResponse)
def resume_source(source_id: str, db: Session = Depends(get_db)):
    try:
        return IntegrationManager(db).set_source_paused(source_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not IntegrationManager(db).delete_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"deleted": True}
