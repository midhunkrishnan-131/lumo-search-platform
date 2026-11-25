"""Crawler API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.crawler.engine import crawler_engine
from app.crawler.validator import validate_and_screen_url
from app.database.connection import get_db, get_engine
from app.models.crawler import CrawlSession, CrawlUrl
from app.schemas.crawler import (
    CrawlSessionListResponse,
    CrawlSessionResponse,
    CrawlUrlListResponse,
    CrawlUrlSummary,
    CreateCrawlSessionRequest,
)
from app.schemas.document import (
    DocumentListResponse,
    DocumentMetadataResponse,
)
from app.models.document import Document

logger = get_logger("api.crawler")
router = APIRouter(prefix="/crawler", tags=["crawler"])


def _check_db_configured() -> None:
    if get_engine() is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not configured or unavailable.",
        )


def _build_session_summary(session_rec: CrawlSession, db: Session) -> CrawlSessionResponse:
    counts = (
        db.query(CrawlUrl.status, func.count(CrawlUrl.id))
        .filter(CrawlUrl.session_id == session_rec.id)
        .group_by(CrawlUrl.status)
        .all()
    )
    status_map = dict(counts)
    seeds_count = (
        db.query(func.count(CrawlUrl.id))
        .filter(CrawlUrl.session_id == session_rec.id, CrawlUrl.is_seed.is_(True))
        .scalar()
        or 0
    )

    return CrawlSessionResponse(
        id=session_rec.id,
        name=session_rec.name,
        status=session_rec.status,
        max_depth=session_rec.max_depth,
        max_pages=session_rec.max_pages,
        crawl_delay=session_rec.crawl_delay,
        pages_crawled=session_rec.pages_crawled,
        created_at=session_rec.created_at,
        started_at=session_rec.started_at,
        completed_at=session_rec.completed_at,
        error_message=session_rec.error_message,
        seeds_count=seeds_count,
        queued_count=status_map.get("queued", 0),
        fetched_count=status_map.get("fetched", 0),
        failed_count=status_map.get("failed", 0),
        skipped_count=status_map.get("skipped", 0),
    )


@router.post(
    "/sessions",
    response_model=CrawlSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a crawl session with seed URLs",
)
def create_session(
    payload: CreateCrawlSessionRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CrawlSessionResponse:
    _check_db_configured()

    # 1. Screen and normalize each seed URL
    validated_seeds: list[tuple[str, str]] = []  # (raw_url, normalized_url)
    seen_normalized: set[str] = set()

    for seed in payload.seed_urls:
        screen = validate_and_screen_url(seed)
        if not screen.is_valid:
            logger.warning("Seed URL validation failed for '%s': %s", seed, screen.error)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid seed URL '{seed}': {screen.error}",
            )
        if screen.normalized_url not in seen_normalized:
            seen_normalized.add(screen.normalized_url)
            validated_seeds.append((seed, screen.normalized_url))

    if not validated_seeds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one valid, unique seed URL is required.",
        )

    # 2. Persist new session
    session_rec = CrawlSession(
        name=payload.name or f"Crawl Session ({len(validated_seeds)} seeds)",
        status="pending",
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
        crawl_delay=payload.crawl_delay,
    )
    db.add(session_rec)
    db.flush()

    # 3. Add seed URLs to session
    for raw_url, normalized in validated_seeds:
        url_rec = CrawlUrl(
            session_id=session_rec.id,
            url=raw_url,
            normalized_url=normalized,
            depth=0,
            is_seed=True,
            status="queued",
        )
        db.add(url_rec)

    db.commit()
    db.refresh(session_rec)

    logger.info("Created crawl session %s with %s seed URLs", session_rec.id, len(validated_seeds))
    return _build_session_summary(session_rec, db)


@router.post(
    "/sessions/{session_id}/start",
    response_model=CrawlSessionResponse,
    summary="Start crawling a session",
)
async def start_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CrawlSessionResponse:
    _check_db_configured()

    session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found.")

    if session_rec.status == "running":
        return _build_session_summary(session_rec, db)

    if session_rec.status in {"completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start session in '{session_rec.status}' status.",
        )

    # Launch background crawling task
    from app.database.connection import _session_factory

    if _session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database session factory is not available.",
        )

    await crawler_engine.start_session(
        session_id=session_id,
        session_factory=_session_factory,
        user_agent=settings.crawler_user_agent,
        request_timeout=settings.crawler_request_timeout,
        max_response_size=settings.crawler_max_response_size,
    )

    db.refresh(session_rec)
    return _build_session_summary(session_rec, db)


@router.post(
    "/sessions/{session_id}/stop",
    response_model=CrawlSessionResponse,
    summary="Stop an active crawl session",
)
def stop_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CrawlSessionResponse:
    _check_db_configured()

    session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found.")

    crawler_engine.stop_session(session_id)

    db.refresh(session_rec)
    return _build_session_summary(session_rec, db)


@router.get(
    "/sessions/{session_id}",
    response_model=CrawlSessionResponse,
    summary="Get crawl session status",
)
def get_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CrawlSessionResponse:
    _check_db_configured()

    session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found.")

    return _build_session_summary(session_rec, db)


@router.get(
    "/sessions",
    response_model=CrawlSessionListResponse,
    summary="List crawl sessions",
)
def list_sessions(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CrawlSessionListResponse:
    _check_db_configured()

    total = db.query(func.count(CrawlSession.id)).scalar() or 0
    records = (
        db.query(CrawlSession)
        .order_by(CrawlSession.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    summaries = [_build_session_summary(r, db) for r in records]
    return CrawlSessionListResponse(total=total, sessions=summaries)


@router.get(
    "/sessions/{session_id}/urls",
    response_model=CrawlUrlListResponse,
    summary="List URLs for a crawl session",
)
def list_session_urls(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CrawlUrlListResponse:
    _check_db_configured()

    session_rec = db.query(CrawlSession.id).filter(CrawlSession.id == session_id).first()
    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found.")

    query = db.query(CrawlUrl).filter(CrawlUrl.session_id == session_id)
    if status_filter:
        query = query.filter(CrawlUrl.status == status_filter)

    total = query.count()
    records = query.order_by(CrawlUrl.depth.asc(), CrawlUrl.id.asc()).offset(offset).limit(limit).all()

    return CrawlUrlListResponse(
        session_id=session_id,
        total=total,
        urls=[CrawlUrlSummary.model_validate(r) for r in records],
    )


@router.get(
    "/sessions/{session_id}/documents",
    response_model=DocumentListResponse,
    summary="List extracted documents for a crawl session",
)
def list_session_documents(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    is_duplicate: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    _check_db_configured()

    session_rec = db.query(CrawlSession.id).filter(CrawlSession.id == session_id).first()
    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found.")

    query = db.query(Document).filter(Document.session_id == session_id)
    if is_duplicate is not None:
        query = query.filter(Document.is_duplicate == is_duplicate)

    total = query.count()
    records = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    return DocumentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        documents=[DocumentMetadataResponse.model_validate(r) for r in records],
    )
