"""FastAPI endpoints for persistent search and browsing history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.history.service import (
    clear_browsing_history,
    clear_search_history,
    delete_browsing_history_item,
    delete_search_history_item,
    export_history,
    list_browsing_history,
    list_search_history,
    record_browsing,
)
from app.schemas.history import (
    BrowsingHistoryItem,
    BrowsingHistoryListResponse,
    ClearHistoryResponse,
    RecordBrowseRequest,
    SearchHistoryItem,
    SearchHistoryListResponse,
)

logger = get_logger("api.history")

router = APIRouter(prefix="/history", tags=["history"])


# --- Search History Endpoints ---


@router.get(
    "/search",
    response_model=SearchHistoryListResponse,
    summary="List search history",
    description="Retrieve paginated search history records.",
)
def get_search_history(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session_id: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> SearchHistoryListResponse:
    total, records = list_search_history(db, limit=limit, offset=offset, session_id=session_id)
    return SearchHistoryListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[SearchHistoryItem.model_validate(r) for r in records],
    )


@router.delete(
    "/search/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete search history item",
)
def delete_search_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> None:
    deleted = delete_search_history_item(db, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search history item '{item_id}' not found",
        )


@router.delete(
    "/search",
    response_model=ClearHistoryResponse,
    summary="Clear all search history",
)
def clear_all_searches(
    session_id: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ClearHistoryResponse:
    count = clear_search_history(db, session_id=session_id)
    return ClearHistoryResponse(success=True, deleted_count=count)


# --- Browsing History Endpoints ---


@router.post(
    "/browse",
    response_model=BrowsingHistoryItem,
    status_code=status.HTTP_201_CREATED,
    summary="Record a browsing / click event",
    description="Records when a user visits a search result or webpage.",
)
def log_browse_event(
    payload: RecordBrowseRequest,
    privacy: Annotated[bool, Query()] = False,
    x_history_disabled: Annotated[bool, Header(alias="X-History-Disabled")] = False,
    db: Session = Depends(get_db),
) -> BrowsingHistoryItem:
    privacy_active = privacy or x_history_disabled
    rec = record_browsing(
        db=db,
        url=payload.url,
        title=payload.title,
        document_id=payload.document_id,
        session_id=payload.session_id,
        dwell_seconds=payload.dwell_seconds,
        referrer=payload.referrer,
        privacy_disabled=privacy_active,
    )
    if not rec:
        # If privacy disabled, return a non-persisted virtual confirmation
        from app.models.history import BrowsingHistory
        rec = BrowsingHistory(
            id="privacy-untracked",
            url=payload.url,
            title=payload.title,
            dwell_seconds=payload.dwell_seconds,
        )
    else:
        db.commit()
        db.refresh(rec)

    return BrowsingHistoryItem.model_validate(rec)


@router.get(
    "/browse",
    response_model=BrowsingHistoryListResponse,
    summary="List browsing history",
    description="Retrieve paginated visited pages history.",
)
def get_browsing_history(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session_id: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> BrowsingHistoryListResponse:
    total, records = list_browsing_history(db, limit=limit, offset=offset, session_id=session_id)
    return BrowsingHistoryListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[BrowsingHistoryItem.model_validate(r) for r in records],
    )


@router.delete(
    "/browse/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete browsing history item",
)
def delete_browsing_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> None:
    deleted = delete_browsing_history_item(db, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Browsing history item '{item_id}' not found",
        )


@router.delete(
    "/browse",
    response_model=ClearHistoryResponse,
    summary="Clear all browsing history",
)
def clear_all_browsing(
    session_id: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ClearHistoryResponse:
    count = clear_browsing_history(db, session_id=session_id)
    return ClearHistoryResponse(success=True, deleted_count=count)


# --- Privacy & Export Endpoints ---


@router.get(
    "/export",
    summary="Export complete history",
    description="Export search and browsing history records as a JSON bundle for data portability.",
)
def export_user_history(
    session_id: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> dict:
    return export_history(db, session_id=session_id)
