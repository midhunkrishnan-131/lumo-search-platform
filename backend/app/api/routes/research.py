"""FastAPI router for LUMO Phase 9 Autonomous Research Agent."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.research.manager import research_manager
from app.schemas.research import (
    ResearchCreateRequest,
    ResearchReportResponse,
    ResearchSessionDetailResponse,
    ResearchSessionListResponse,
    ResearchSessionResponse,
)

logger = get_logger("api.research")

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "",
    response_model=ResearchSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new research session",
    description="Initializes a multi-step bounded autonomous research session. If auto_start is true, kicks off background execution.",
)
def create_research_session(
    request: ResearchCreateRequest,
    db: Session = Depends(get_db),
) -> ResearchSessionResponse:
    if not request.query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Research query or topic cannot be empty.",
        )

    session = research_manager.create_session(
        db=db,
        topic=request.query,
        max_iterations=request.max_iterations,
        max_queries=request.max_queries,
        max_sources=request.max_sources,
        provider=request.provider,
    )

    if request.auto_start:
        research_manager.start_session(session.id, background=True)

    return ResearchSessionResponse.model_validate(session)


@router.post(
    "/{session_id}/start",
    response_model=ResearchSessionResponse,
    summary="Start an existing pending research session",
)
def start_research_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ResearchSessionResponse:
    session = research_manager.get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")

    if session.status != "pending":
        return ResearchSessionResponse.model_validate(session)

    started = research_manager.start_session(session_id, background=True)
    return ResearchSessionResponse.model_validate(started or session)


@router.get(
    "/{session_id}",
    response_model=ResearchSessionDetailResponse,
    summary="Get research session details and live status",
)
def get_research_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ResearchSessionDetailResponse:
    session = research_manager.get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")
    return ResearchSessionDetailResponse.model_validate(session)


@router.get(
    "/{session_id}/report",
    response_model=ResearchReportResponse,
    summary="Get completed research report and citations",
)
def get_research_report(
    session_id: str,
    db: Session = Depends(get_db),
) -> ResearchReportResponse:
    session = research_manager.get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")

    return ResearchReportResponse(
        session_id=session.id,
        topic=session.topic,
        status=session.status,
        report_markdown=session.report_markdown or "",
        plan=session.plan or {},
        sources=session.sources or [],
        findings=session.findings or [],
        completed_at=session.completed_at,
    )


@router.get(
    "/{session_id}/sources",
    summary="Get collected sources for a research session",
)
def get_research_sources(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    session = research_manager.get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")
    return session.sources or []


@router.post(
    "/{session_id}/cancel",
    response_model=ResearchSessionResponse,
    summary="Cancel an active research session",
)
def cancel_research_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ResearchSessionResponse:
    session = research_manager.cancel_session(session_id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")
    return ResearchSessionResponse.model_validate(session)


@router.get(
    "",
    response_model=ResearchSessionListResponse,
    summary="List research sessions with pagination",
)
def list_research_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ResearchSessionListResponse:
    items, total = research_manager.list_sessions(db, limit=limit, offset=offset)
    return ResearchSessionListResponse(
        items=[ResearchSessionResponse.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a research session",
)
def delete_research_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> None:
    deleted = research_manager.delete_session(session_id, db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research session not found")
