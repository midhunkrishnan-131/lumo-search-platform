"""FastAPI routes for LUMO Phase 27: Unified Intelligence Workspace & Orchestration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowDetailResponse,
    WorkflowExecuteRequest,
    WorkflowResponse,
)
from app.workflows.engine import WorkflowManager

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _resolve_owner(x_lumo_owner: str | None = Header(default=None, alias="X-LUMO-Owner")) -> str:
    cleaned = (x_lumo_owner or "").strip()
    return cleaned[:120] if cleaned else "local"


@router.post("", response_model=WorkflowDetailResponse, status_code=201)
def create_workflow(
    payload: WorkflowCreateRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    """Classify request intent and build a workflow plan without silently executing it."""
    return WorkflowManager(db).create_and_plan(payload, owner_id=owner_id)


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(
    intent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    return WorkflowManager(db).list_workflows(owner_id=owner_id, intent=intent, status=status, q=q, limit=limit)


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow(
    workflow_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        return WorkflowManager(db).get_workflow(workflow_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workflow_id}/execute", response_model=WorkflowDetailResponse)
def execute_workflow(
    workflow_id: str,
    payload: WorkflowExecuteRequest | None = None,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        return WorkflowManager(db).execute_workflow(workflow_id, owner_id=owner_id, payload=payload)
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{workflow_id}/cancel", response_model=WorkflowDetailResponse)
def cancel_workflow(
    workflow_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        return WorkflowManager(db).cancel_workflow(workflow_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workflow_id}/retry", response_model=WorkflowDetailResponse)
def retry_workflow(
    workflow_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        return WorkflowManager(db).retry_failed_steps(workflow_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_id}/export")
def export_workflow(
    workflow_id: str,
    format: str = Query(default="json"),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    try:
        content, media = WorkflowManager(db).export_workflow(workflow_id, owner_id=owner_id, fmt=format)
        return Response(content=content, media_type=media)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not WorkflowManager(db).delete_workflow(workflow_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return {"deleted": True}
