"""FastAPI operational endpoints for LUMO Phase 21: Diagnostics, Release, Backup & Restore."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.ops.backup import create_backup, list_backups, prune_backups, restore_backup, verify_backup
from app.ops.diagnostics import run_deployment_diagnostics
from app.ops.migrations import CURRENT_SCHEMA_VERSION, get_migration_status

router = APIRouter(prefix="/ops", tags=["operations"])


class RestoreRequest(BaseModel):
    confirm: bool = False


@router.get("/diagnostics")
def ops_diagnostics(request: Request) -> dict[str, Any]:
    """Run deployment, dependency, database, vector store, AI, and storage diagnostics."""
    return run_deployment_diagnostics(request.app.state.settings)


@router.get("/release")
def ops_release(request: Request) -> dict[str, Any]:
    """Return LUMO version, build phase, environment, and schema migration status."""
    cfg = request.app.state.settings
    mig = get_migration_status()
    return {
        "application": cfg.app_name,
        "version": cfg.app_version,
        "phase": "26",
        "environment": cfg.environment,
        "schema_version": mig.get("current_version", 0),
        "target_schema_version": CURRENT_SCHEMA_VERSION,
        "migration_status": mig.get("status"),
    }


@router.get("/backups")
def ops_list_backups() -> list[dict[str, Any]]:
    return list_backups()


@router.post("/backups", status_code=201)
def ops_create_backup(request: Request, label: str = Query(default="manual", max_length=64)) -> dict[str, Any]:
    try:
        return create_backup(label=label, settings=request.app.state.settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {type(exc).__name__}") from exc


@router.post("/backups/{backup_id}/verify")
def ops_verify_backup(backup_id: str) -> dict[str, Any]:
    res = verify_backup(backup_id)
    if not res["valid"] and res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return res


@router.post("/backups/prune")
def ops_prune_backups(keep: int = Query(default=5, ge=1, le=50)) -> dict[str, Any]:
    return prune_backups(keep=keep)


@router.post("/backups/{backup_id}/restore")
def ops_restore_backup(backup_id: str, payload: RestoreRequest, request: Request) -> dict[str, Any]:
    try:
        return restore_backup(
            backup_id=backup_id,
            confirm=payload.confirm,
            settings=request.app.state.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
