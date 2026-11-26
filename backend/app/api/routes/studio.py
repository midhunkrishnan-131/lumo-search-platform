"""FastAPI routes for LUMO Phase 30: Intelligence Studio."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.studio import (
    StudioAIAssistRequest,
    StudioProjectCreate,
    StudioProjectUpdate,
    StudioSaveKnowledgeRequest,
    StudioSourceImportRequest,
)
from app.studio.service import StudioService
from app.studio.templates import STUDIO_TEMPLATES

router = APIRouter(prefix="/studio", tags=["intelligence-studio"])


def _resolve_owner(x_lumo_owner: str | None = Header(default=None, alias="X-LUMO-Owner")) -> str:
    cleaned = (x_lumo_owner or "").strip()
    return cleaned[:120] if cleaned else "local"


@router.get("/templates")
def list_templates() -> list[dict[str, Any]]:
    return list(STUDIO_TEMPLATES.values())


@router.get("/projects")
def list_projects(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return StudioService(db).list_projects(owner_id=owner_id)


@router.post("/projects", status_code=201)
def create_project(
    payload: StudioProjectCreate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return StudioService(db).create_project(payload, owner_id=owner_id)


@router.get("/projects/{project_id}")
def get_project(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return StudioService(db).get_project(project_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/projects/{project_id}")
def update_project(
    project_id: str,
    payload: StudioProjectUpdate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return StudioService(db).update_project(project_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return StudioService(db).duplicate_project(project_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, bool]:
    if not StudioService(db).delete_project(project_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Studio project not found.")
    return {"deleted": True}


@router.post("/projects/{project_id}/import")
def import_source(
    project_id: str,
    payload: StudioSourceImportRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return StudioService(db).import_source(project_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/ai-assist")
def ai_assist(
    project_id: str,
    payload: StudioAIAssistRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return StudioService(db).ai_assist(project_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/citations/validate")
def validate_citations(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return StudioService(db).validate_citations(project_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        return StudioService(db).list_versions(project_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/versions/{version_id}/restore")
def restore_version(
    project_id: str,
    version_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return StudioService(db).restore_version(project_id, version_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/presentation-outline")
def presentation_outline(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return StudioService(db).generate_presentation_outline(project_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/preview")
def preview_project(project_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)):
    try:
        html_txt, media = StudioService(db).export_project(project_id, owner_id=owner_id, fmt="html")
        return Response(content=html_txt, media_type=media)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/export")
def export_project(
    project_id: str,
    format: str = Query(default="markdown"),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        content, media = StudioService(db).export_project(project_id, owner_id=owner_id, fmt=format)
        return Response(content=content, media_type=media)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/save-to-knowledge")
def save_to_knowledge(
    project_id: str,
    payload: StudioSaveKnowledgeRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return StudioService(db).save_to_knowledge_hub(project_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
