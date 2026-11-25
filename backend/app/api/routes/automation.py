"""FastAPI routes for LUMO Phase 16: Intelligence Automation Engine."""

from __future__ import annotations

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.automation.engine import automation_manager, compute_next_run, utc_now
from app.automation.templates import AUTOMATION_TEMPLATES
from app.core.logging import get_logger
from app.database.connection import get_db
from app.models.automation import (
    Automation,
    AutomationExecution,
    AutomationExecutionStep,
    AutomationNotification,
)
from app.schemas.automation import (
    AutomationCreate,
    AutomationExecutionResponse,
    AutomationNotificationResponse,
    AutomationResponse,
    AutomationStepLogResponse,
    AutomationTemplateResponse,
    AutomationUpdate,
)

logger = get_logger("api.automation")

automations_router = APIRouter(prefix="/automations", tags=["automations"])
executions_router = APIRouter(prefix="/automation-executions", tags=["automations"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


def _exec_to_response(ex: AutomationExecution) -> AutomationExecutionResponse:
    return AutomationExecutionResponse(
        id=ex.id,
        automation_id=ex.automation_id,
        automation_name=ex.automation.name if ex.automation else None,
        trigger_source=ex.trigger_source,
        status=ex.status,
        current_step_index=ex.current_step_index,
        total_steps=ex.total_steps,
        retry_count=ex.retry_count,
        output_summary=ex.output_summary,
        workspace_item_id=ex.workspace_item_id,
        error_message=ex.error_message,
        started_at=ex.started_at,
        completed_at=ex.completed_at,
        created_at=ex.created_at,
        step_logs=[AutomationStepLogResponse.model_validate(s) for s in ex.step_logs],
    )


# --- Automations CRUD & Lifecycle ---


@automations_router.get("/templates", response_model=list[AutomationTemplateResponse], summary="List Automation Templates")
def list_templates() -> list[AutomationTemplateResponse]:
    return AUTOMATION_TEMPLATES


@automations_router.get("", response_model=list[AutomationResponse], summary="List Automations")
def list_automations(
    enabled: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
) -> list[AutomationResponse]:
    q = db.query(Automation)
    if enabled is not None:
        q = q.filter(Automation.enabled == enabled)
    rows = q.order_by(Automation.created_at.desc()).limit(limit).all()
    return [AutomationResponse.model_validate(r) for r in rows]


@automations_router.post(
    "",
    response_model=AutomationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Automation",
)
def create_automation(
    payload: AutomationCreate,
    db: Session = Depends(get_db),
) -> AutomationResponse:
    next_run = (
        compute_next_run(payload.trigger_type, payload.trigger_config)
        if payload.enabled and payload.trigger_type == "scheduled"
        else None
    )
    auto = Automation(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        description=payload.description,
        workflow_type=payload.workflow_type,
        trigger_type=payload.trigger_type,
        trigger_config=payload.trigger_config,
        steps=[s.model_dump() for s in payload.steps],
        output_config=payload.output_config,
        enabled=payload.enabled,
        max_executions_per_day=payload.max_executions_per_day,
        timeout_seconds=payload.timeout_seconds,
        max_retries=payload.max_retries,
        next_run_at=next_run,
    )
    db.add(auto)
    db.commit()
    db.refresh(auto)
    return AutomationResponse.model_validate(auto)


@automations_router.get("/{automation_id}", response_model=AutomationResponse, summary="Get Automation")
def get_automation(automation_id: str, db: Session = Depends(get_db)) -> AutomationResponse:
    auto = db.query(Automation).filter(Automation.id == automation_id).first()
    if not auto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    return AutomationResponse.model_validate(auto)


@automations_router.put("/{automation_id}", response_model=AutomationResponse, summary="Update Automation")
def update_automation(
    automation_id: str,
    payload: AutomationUpdate,
    db: Session = Depends(get_db),
) -> AutomationResponse:
    auto = db.query(Automation).filter(Automation.id == automation_id).first()
    if not auto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")

    if payload.name is not None:
        auto.name = payload.name.strip()
    if payload.description is not None:
        auto.description = payload.description
    if payload.workflow_type is not None:
        auto.workflow_type = payload.workflow_type
    if payload.trigger_type is not None:
        auto.trigger_type = payload.trigger_type
    if payload.trigger_config is not None:
        auto.trigger_config = payload.trigger_config
    if payload.steps is not None:
        auto.steps = [s.model_dump() for s in payload.steps]
    if payload.output_config is not None:
        auto.output_config = payload.output_config
    if payload.enabled is not None:
        auto.enabled = payload.enabled
    if payload.max_executions_per_day is not None:
        auto.max_executions_per_day = payload.max_executions_per_day
    if payload.timeout_seconds is not None:
        auto.timeout_seconds = payload.timeout_seconds
    if payload.max_retries is not None:
        auto.max_retries = payload.max_retries

    auto.version += 1
    auto.next_run_at = (
        compute_next_run(auto.trigger_type, auto.trigger_config)
        if auto.enabled and auto.trigger_type == "scheduled"
        else None
    )
    auto.updated_at = utc_now()
    db.commit()
    db.refresh(auto)
    return AutomationResponse.model_validate(auto)


@automations_router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Automation")
def delete_automation(automation_id: str, db: Session = Depends(get_db)) -> None:
    auto = db.query(Automation).filter(Automation.id == automation_id).first()
    if not auto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    db.delete(auto)
    db.commit()


@automations_router.post("/{automation_id}/run", response_model=AutomationExecutionResponse, summary="Run Automation Manually")
def run_automation(
    automation_id: str,
    sync: Annotated[bool, Query(description="Run synchronously (useful for immediate testing)")] = False,
    db: Session = Depends(get_db),
) -> AutomationExecutionResponse:
    try:
        ex = automation_manager.trigger_automation(
            db, automation_id=automation_id, trigger_source="manual", run_sync=sync
        )
        return _exec_to_response(ex)
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@automations_router.post("/{automation_id}/pause", response_model=AutomationResponse, summary="Pause Automation")
def pause_automation(automation_id: str, db: Session = Depends(get_db)) -> AutomationResponse:
    auto = db.query(Automation).filter(Automation.id == automation_id).first()
    if not auto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    auto.enabled = False
    auto.next_run_at = None
    auto.updated_at = utc_now()
    db.commit()
    db.refresh(auto)
    return AutomationResponse.model_validate(auto)


@automations_router.post("/{automation_id}/resume", response_model=AutomationResponse, summary="Resume Automation")
def resume_automation(automation_id: str, db: Session = Depends(get_db)) -> AutomationResponse:
    auto = db.query(Automation).filter(Automation.id == automation_id).first()
    if not auto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    auto.enabled = True
    auto.next_run_at = compute_next_run(auto.trigger_type, auto.trigger_config)
    auto.updated_at = utc_now()
    db.commit()
    db.refresh(auto)
    return AutomationResponse.model_validate(auto)


@automations_router.post(
    "/{automation_id}/duplicate",
    response_model=AutomationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate Automation",
)
def duplicate_automation(automation_id: str, db: Session = Depends(get_db)) -> AutomationResponse:
    src = db.query(Automation).filter(Automation.id == automation_id).first()
    if not src:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    copy_auto = Automation(
        id=str(uuid.uuid4()),
        name=f"{src.name} (Copy)"[:200],
        description=src.description,
        workflow_type=src.workflow_type,
        trigger_type=src.trigger_type,
        trigger_config=dict(src.trigger_config or {}),
        steps=list(src.steps or []),
        output_config=dict(src.output_config or {}),
        enabled=False,
        max_executions_per_day=src.max_executions_per_day,
        timeout_seconds=src.timeout_seconds,
        max_retries=src.max_retries,
    )
    db.add(copy_auto)
    db.commit()
    db.refresh(copy_auto)
    return AutomationResponse.model_validate(copy_auto)


# --- Executions ---


@executions_router.get("", response_model=list[AutomationExecutionResponse], summary="List Automation Executions")
def list_executions(
    automation_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_db),
) -> list[AutomationExecutionResponse]:
    q = db.query(AutomationExecution)
    if automation_id:
        q = q.filter(AutomationExecution.automation_id == automation_id)
    if status_filter:
        q = q.filter(AutomationExecution.status == status_filter)
    rows = q.order_by(AutomationExecution.created_at.desc()).limit(limit).all()
    return [_exec_to_response(r) for r in rows]


@executions_router.get("/{execution_id}", response_model=AutomationExecutionResponse, summary="Get Execution Details")
def get_execution(execution_id: str, db: Session = Depends(get_db)) -> AutomationExecutionResponse:
    ex = db.query(AutomationExecution).filter(AutomationExecution.id == execution_id).first()
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")
    return _exec_to_response(ex)


@executions_router.post("/{execution_id}/cancel", response_model=AutomationExecutionResponse, summary="Cancel Execution")
def cancel_execution(execution_id: str, db: Session = Depends(get_db)) -> AutomationExecutionResponse:
    ex = automation_manager.cancel_execution(db, execution_id)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")
    return _exec_to_response(ex)


@executions_router.get("/{execution_id}/logs", response_model=list[AutomationStepLogResponse], summary="Get Execution Step Logs")
def get_execution_logs(execution_id: str, db: Session = Depends(get_db)) -> list[AutomationStepLogResponse]:
    ex = db.query(AutomationExecution).filter(AutomationExecution.id == execution_id).first()
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")
    rows = (
        db.query(AutomationExecutionStep)
        .filter(AutomationExecutionStep.execution_id == execution_id)
        .order_by(AutomationExecutionStep.id.asc())
        .all()
    )
    return [AutomationStepLogResponse.model_validate(r) for r in rows]


# --- Notifications ---


@notifications_router.get("", response_model=list[AutomationNotificationResponse], summary="List Notifications")
def list_notifications(
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_db),
) -> list[AutomationNotificationResponse]:
    q = db.query(AutomationNotification)
    if unread_only:
        q = q.filter(AutomationNotification.is_read == False)  # noqa: E712
    rows = q.order_by(AutomationNotification.created_at.desc()).limit(limit).all()
    return [AutomationNotificationResponse.model_validate(r) for r in rows]


@notifications_router.post("/{notification_id}/read", response_model=AutomationNotificationResponse, summary="Mark Notification Read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db)) -> AutomationNotificationResponse:
    notif = db.query(AutomationNotification).filter(AutomationNotification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return AutomationNotificationResponse.model_validate(notif)


@notifications_router.post("/read-all", summary="Mark All Notifications Read")
def mark_all_notifications_read(db: Session = Depends(get_db)) -> dict[str, int]:
    updated = (
        db.query(AutomationNotification)
        .filter(AutomationNotification.is_read == False)  # noqa: E712
        .update({"is_read": True})
    )
    db.commit()
    return {"marked_read": updated}


@notifications_router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Notification")
def delete_notification(notification_id: str, db: Session = Depends(get_db)) -> None:
    notif = db.query(AutomationNotification).filter(AutomationNotification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    db.delete(notif)
    db.commit()
