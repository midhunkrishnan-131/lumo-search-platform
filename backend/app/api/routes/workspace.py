"""FastAPI routes for LUMO Phase 14: Personal Intelligence & Knowledge Workspace."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.router import AIProviderRouter
from app.core.logging import get_logger
from app.database.connection import get_db
from app.schemas.workspace import (
    WorkspaceAnnotationCreate,
    WorkspaceAnnotationResponse,
    WorkspaceAnnotationUpdate,
    WorkspaceAskRequest,
    WorkspaceAskResponse,
    WorkspaceCollectionCreate,
    WorkspaceCollectionResponse,
    WorkspaceCollectionUpdate,
    WorkspaceConnectionsResponse,
    WorkspaceDashboardResponse,
    WorkspaceItemCreate,
    WorkspaceItemListResponse,
    WorkspaceItemResponse,
    WorkspaceItemUpdate,
    WorkspaceNoteCreate,
    WorkspaceNoteResponse,
    WorkspaceNoteUpdate,
    WorkspaceSearchRequest,
    WorkspaceSearchResponse,
    WorkspaceStatsResponse,
    WorkspaceTagCreate,
    WorkspaceTagSchema,
    WorkspaceUrlImportRequest,
)
from app.workspace.ai import WorkspaceAIOrchestrator
from app.workspace.importer import MAX_IMPORT_BYTES, WorkspaceImporter
from app.workspace.search import WorkspaceSearchEngine
from app.workspace.service import WorkspaceService

logger = get_logger("api.workspace")

router = APIRouter(prefix="/workspace", tags=["workspace"])

_ai_router: AIProviderRouter | None = None


def get_ai_router() -> AIProviderRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AIProviderRouter()
    return _ai_router


# --- Dashboard & Stats ---


@router.get("", response_model=WorkspaceDashboardResponse, summary="Workspace Dashboard")
def get_workspace_dashboard(db: Session = Depends(get_db)) -> WorkspaceDashboardResponse:
    return WorkspaceService(db).get_dashboard()


@router.get("/stats", response_model=WorkspaceStatsResponse, summary="Workspace Statistics")
def get_workspace_stats(db: Session = Depends(get_db)) -> WorkspaceStatsResponse:
    return WorkspaceService(db).get_stats()


# --- Items ---


@router.get("/items", response_model=WorkspaceItemListResponse, summary="List Workspace Items")
def list_workspace_items(
    collection_id: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> WorkspaceItemListResponse:
    return WorkspaceService(db).list_items(
        collection_id=collection_id,
        source_type=source_type,
        tag=tag,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/items",
    response_model=WorkspaceItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save Item to Workspace",
)
def create_workspace_item(
    payload: WorkspaceItemCreate,
    db: Session = Depends(get_db),
) -> WorkspaceItemResponse:
    try:
        return WorkspaceService(db).create_item(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/items/{item_id}", response_model=WorkspaceItemResponse, summary="Get Workspace Item")
def get_workspace_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> WorkspaceItemResponse:
    item = WorkspaceService(db).get_item(item_id, mark_viewed=True)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace item not found.")
    return item


@router.patch("/items/{item_id}", response_model=WorkspaceItemResponse, summary="Update Workspace Item")
def update_workspace_item(
    item_id: str,
    payload: WorkspaceItemUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceItemResponse:
    try:
        item = WorkspaceService(db).update_item(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace item not found.")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Workspace Item")
def delete_workspace_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> None:
    if not WorkspaceService(db).delete_item(item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace item not found.")


@router.get(
    "/items/{item_id}/connections",
    response_model=WorkspaceConnectionsResponse,
    summary="Knowledge Graph Connections for Workspace Item",
)
def get_item_connections(
    item_id: str,
    db: Session = Depends(get_db),
) -> WorkspaceConnectionsResponse:
    res = WorkspaceService(db).get_item_connections(item_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace item not found.")
    return res


# --- Document & URL Import ---


@router.post(
    "/import",
    response_model=WorkspaceItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import Personal Document (PDF, TXT, MD, HTML, DOCX)",
)
async def import_workspace_file(
    file: UploadFile = File(...),
    collection_id: str | None = Form(None),
    tags: str = Form(""),
    db: Session = Depends(get_db),
) -> WorkspaceItemResponse:
    raw_bytes = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw_bytes) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit.",
        )

    importer = WorkspaceImporter()
    try:
        parsed = importer.import_bytes(file.filename or "document", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    item_payload = WorkspaceItemCreate(
        title=parsed.title,
        content=parsed.content,
        summary=parsed.summary,
        source_type="document_import",
        source_url=None,
        collection_id=collection_id or None,
        tags=tag_list,
        metadata=parsed.metadata,
    )
    try:
        return WorkspaceService(db).create_item(
            item_payload,
            file_name=parsed.file_name,
            file_type=parsed.file_type,
            content_hash_override=parsed.content_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/import-url",
    response_model=WorkspaceItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import Web Page Safely into Workspace",
)
def import_workspace_url(
    payload: WorkspaceUrlImportRequest,
    db: Session = Depends(get_db),
) -> WorkspaceItemResponse:
    importer = WorkspaceImporter()
    try:
        parsed = importer.import_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    item_payload = WorkspaceItemCreate(
        title=parsed.title,
        content=parsed.content,
        summary=parsed.summary,
        source_type="web_page",
        source_url=parsed.source_url,
        collection_id=payload.collection_id or None,
        tags=payload.tags,
        metadata=parsed.metadata,
    )
    try:
        return WorkspaceService(db).create_item(
            item_payload,
            file_type="html",
            content_hash_override=parsed.content_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Collections ---


@router.get("/collections", response_model=list[WorkspaceCollectionResponse], summary="List Collections")
def list_collections(db: Session = Depends(get_db)) -> list[WorkspaceCollectionResponse]:
    return WorkspaceService(db).list_collections()


@router.post(
    "/collections",
    response_model=WorkspaceCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Collection",
)
def create_collection(
    payload: WorkspaceCollectionCreate,
    db: Session = Depends(get_db),
) -> WorkspaceCollectionResponse:
    try:
        return WorkspaceService(db).create_collection(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/collections/{collection_id}", response_model=WorkspaceCollectionResponse, summary="Get Collection")
def get_collection(collection_id: str, db: Session = Depends(get_db)) -> WorkspaceCollectionResponse:
    col = WorkspaceService(db).get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return col


@router.patch("/collections/{collection_id}", response_model=WorkspaceCollectionResponse, summary="Update Collection")
def update_collection(
    collection_id: str,
    payload: WorkspaceCollectionUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceCollectionResponse:
    try:
        col = WorkspaceService(db).update_collection(collection_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return col


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Collection")
def delete_collection(collection_id: str, db: Session = Depends(get_db)) -> None:
    if not WorkspaceService(db).delete_collection(collection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")


# --- Notes ---


@router.get("/notes", response_model=list[WorkspaceNoteResponse], summary="List Notes")
def list_notes(
    collection_id: Annotated[str | None, Query()] = None,
    linked_item_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
) -> list[WorkspaceNoteResponse]:
    return WorkspaceService(db).list_notes(
        collection_id=collection_id, linked_item_id=linked_item_id, limit=limit
    )


@router.post(
    "/notes",
    response_model=WorkspaceNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Note",
)
def create_note(
    payload: WorkspaceNoteCreate,
    db: Session = Depends(get_db),
) -> WorkspaceNoteResponse:
    return WorkspaceService(db).create_note(payload)


@router.get("/notes/{note_id}", response_model=WorkspaceNoteResponse, summary="Get Note")
def get_note(note_id: str, db: Session = Depends(get_db)) -> WorkspaceNoteResponse:
    note = WorkspaceService(db).get_note(note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    return note


@router.patch("/notes/{note_id}", response_model=WorkspaceNoteResponse, summary="Update / Autosave Note")
def update_note(
    note_id: str,
    payload: WorkspaceNoteUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceNoteResponse:
    note = WorkspaceService(db).update_note(note_id, payload)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Note")
def delete_note(note_id: str, db: Session = Depends(get_db)) -> None:
    if not WorkspaceService(db).delete_note(note_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")


# --- Tags ---


@router.get("/tags", response_model=list[WorkspaceTagSchema], summary="List Tags")
def list_tags(db: Session = Depends(get_db)) -> list[WorkspaceTagSchema]:
    return WorkspaceService(db).list_tags()


@router.post(
    "/tags",
    response_model=WorkspaceTagSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Tag",
)
def create_tag(payload: WorkspaceTagCreate, db: Session = Depends(get_db)) -> WorkspaceTagSchema:
    try:
        return WorkspaceService(db).create_tag(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Annotations ---


@router.get(
    "/items/{item_id}/annotations",
    response_model=list[WorkspaceAnnotationResponse],
    summary="List Item Annotations",
)
def list_item_annotations(item_id: str, db: Session = Depends(get_db)) -> list[WorkspaceAnnotationResponse]:
    return WorkspaceService(db).list_annotations(item_id)


@router.post(
    "/items/{item_id}/annotations",
    response_model=WorkspaceAnnotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Annotation on Item",
)
def create_item_annotation(
    item_id: str,
    payload: WorkspaceAnnotationCreate,
    db: Session = Depends(get_db),
) -> WorkspaceAnnotationResponse:
    ann = WorkspaceService(db).create_annotation(item_id, payload)
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace item not found.")
    return ann


@router.patch(
    "/annotations/{annotation_id}",
    response_model=WorkspaceAnnotationResponse,
    summary="Update Annotation",
)
def update_annotation(
    annotation_id: str,
    payload: WorkspaceAnnotationUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceAnnotationResponse:
    ann = WorkspaceService(db).update_annotation(annotation_id, payload)
    if not ann:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found.")
    return ann


@router.delete(
    "/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Annotation",
)
def delete_annotation(annotation_id: str, db: Session = Depends(get_db)) -> None:
    if not WorkspaceService(db).delete_annotation(annotation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found.")


# --- Personal Search & AI Knowledge Q&A ---


@router.post("/search", response_model=WorkspaceSearchResponse, summary="Personal Workspace Search")
def search_workspace(
    payload: WorkspaceSearchRequest,
    db: Session = Depends(get_db),
) -> WorkspaceSearchResponse:
    return WorkspaceSearchEngine(db).search(payload)


@router.post("/ask", response_model=WorkspaceAskResponse, summary="Ask Personal Knowledge AI")
def ask_workspace_ai(
    payload: WorkspaceAskRequest,
    db: Session = Depends(get_db),
    ai_router: AIProviderRouter = Depends(get_ai_router),
) -> WorkspaceAskResponse:
    return WorkspaceAIOrchestrator(db, ai_router=ai_router).ask(payload)
