"""FastAPI routes for LUMO Phase 15: Browser Companion Extension."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.models.workspace import WorkspaceItem
from app.schemas.workspace import (
    WorkspaceCollectionResponse,
    WorkspaceItemCreate,
    WorkspaceItemResponse,
    WorkspaceNoteCreate,
    WorkspaceSearchRequest,
    WorkspaceSearchResponse,
)
from app.workspace.search import WorkspaceSearchEngine
from app.workspace.service import WorkspaceService

logger = get_logger("api.extension")

router = APIRouter(prefix="/extension", tags=["browser-extension"])


def _validate_http_url(raw_url: str) -> str:
    cleaned = (raw_url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid http:// or https:// URLs can be saved.",
        )
    return cleaned


class ExtensionSavePageRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(None, max_length=4000)
    canonical_url: str | None = Field(None, max_length=2048)
    favicon_url: str | None = Field(None, max_length=2048)
    selected_text: str | None = Field(None, max_length=50_000)
    note: str | None = Field(None, max_length=20_000)
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ExtensionSaveSelectionRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    title: str = Field(..., min_length=1, max_length=500)
    selected_text: str = Field(..., min_length=1, max_length=50_000)
    note: str | None = Field(None, max_length=20_000)
    collection_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ExtensionSaveResponse(BaseModel):
    item: WorkspaceItemResponse
    note_id: str | None = None
    is_duplicate: bool = False


class ExtensionStatusResponse(BaseModel):
    already_saved: bool
    item_id: str | None = None
    title: str | None = None
    collection_id: str | None = None
    collections: list[WorkspaceCollectionResponse] = Field(default_factory=list)


@router.get("/health", summary="Extension Health Check")
def extension_health() -> dict[str, str]:
    return {"status": "healthy", "application": "LUMO", "extension_api": "v1"}


@router.get("/status", response_model=ExtensionStatusResponse, summary="Check Page Saved Status & Collections")
def extension_status(
    url: Annotated[str | None, Query(max_length=2048)] = None,
    db: Session = Depends(get_db),
) -> ExtensionStatusResponse:
    service = WorkspaceService(db)
    collections = service.list_collections()

    existing: WorkspaceItem | None = None
    if url and url.strip():
        clean_url = url.strip()
        existing = (
            db.query(WorkspaceItem)
            .filter(WorkspaceItem.source_url == clean_url)
            .order_by(WorkspaceItem.created_at.desc())
            .first()
        )

    return ExtensionStatusResponse(
        already_saved=existing is not None,
        item_id=existing.id if existing else None,
        title=existing.title if existing else None,
        collection_id=existing.collection_id if existing else None,
        collections=collections,
    )


@router.post(
    "/save-page",
    response_model=ExtensionSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save Current Web Page from Extension",
)
def extension_save_page(
    payload: ExtensionSavePageRequest,
    db: Session = Depends(get_db),
) -> ExtensionSaveResponse:
    clean_url = _validate_http_url(payload.url)
    service = WorkspaceService(db)

    body_parts = []
    if payload.description:
        body_parts.append(payload.description.strip())
    if payload.selected_text:
        body_parts.append(f"Selected excerpt:\n{payload.selected_text.strip()}")
    content = "\n\n".join(body_parts) or payload.title

    meta: dict[str, Any] = {"captured_via": "browser_extension"}
    if payload.canonical_url:
        meta["canonical_url"] = payload.canonical_url
    if payload.favicon_url:
        meta["favicon_url"] = payload.favicon_url

    try:
        item = service.create_item(
            WorkspaceItemCreate(
                title=payload.title.strip(),
                content=content,
                summary=payload.description,
                source_type="web_page",
                source_url=clean_url,
                collection_id=payload.collection_id or None,
                tags=payload.tags,
                metadata=meta,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    note_id: str | None = None
    if payload.note and payload.note.strip():
        note = service.create_note(
            WorkspaceNoteCreate(
                title=f"Note on {item.title[:180]}",
                content=payload.note.strip(),
                collection_id=item.collection_id,
                linked_item_id=item.id,
                tags=payload.tags,
            )
        )
        note_id = note.id

    return ExtensionSaveResponse(item=item, note_id=note_id, is_duplicate=item.is_duplicate)


@router.post(
    "/save-selection",
    response_model=ExtensionSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save Selected Text from Extension",
)
def extension_save_selection(
    payload: ExtensionSaveSelectionRequest,
    db: Session = Depends(get_db),
) -> ExtensionSaveResponse:
    clean_url = _validate_http_url(payload.url)
    service = WorkspaceService(db)

    try:
        item = service.create_item(
            WorkspaceItemCreate(
                title=f"Excerpt: {payload.title.strip()[:200]}",
                content=payload.selected_text.strip(),
                source_type="selection",
                source_url=clean_url,
                collection_id=payload.collection_id or None,
                tags=payload.tags,
                metadata={"captured_via": "browser_extension", "page_title": payload.title.strip()},
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    note_id: str | None = None
    if payload.note and payload.note.strip():
        note = service.create_note(
            WorkspaceNoteCreate(
                title=f"Note on selection from {payload.title[:140]}",
                content=payload.note.strip(),
                collection_id=item.collection_id,
                linked_item_id=item.id,
                tags=payload.tags,
            )
        )
        note_id = note.id

    return ExtensionSaveResponse(item=item, note_id=note_id, is_duplicate=item.is_duplicate)


@router.get("/search", response_model=WorkspaceSearchResponse, summary="Search Personal Workspace from Extension")
def extension_search(
    q: Annotated[str, Query(max_length=400)] = "",
    mode: Annotated[str, Query(pattern="^(keyword|semantic|hybrid)$")] = "hybrid",
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
    db: Session = Depends(get_db),
) -> WorkspaceSearchResponse:
    return WorkspaceSearchEngine(db).search(
        WorkspaceSearchRequest(
            query=q,
            mode=mode,
            include_notes=True,
            include_annotations=True,
            limit=limit,
        )
    )
