"""FastAPI routes for LUMO Phase 28: Personal Knowledge Hub & Persistent Intelligence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.knowledge_hub.service import KnowledgeHubService
from app.schemas.knowledge_hub import (
    KnowledgeCollectionCreate,
    KnowledgeCollectionUpdate,
    KnowledgeContextRequest,
    KnowledgeImportRequest,
    KnowledgeItemMoveRequest,
    KnowledgeItemSaveRequest,
    KnowledgeNoteCreate,
    KnowledgeNoteUpdate,
    KnowledgeRelationshipCreate,
    KnowledgeSearchRequest,
    KnowledgeTagRenameRequest,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge-hub"])


def _resolve_owner(x_lumo_owner: str | None = Header(default=None, alias="X-LUMO-Owner")) -> str:
    cleaned = (x_lumo_owner or "").strip()
    return cleaned[:120] if cleaned else "local"


@router.get("/dashboard")
def get_dashboard(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    return KnowledgeHubService(db).get_dashboard(owner_id=owner_id)


@router.get("/collections")
def list_collections(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).list_collections(owner_id=owner_id)


@router.post("/collections", status_code=201)
def create_collection(
    payload: KnowledgeCollectionCreate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return KnowledgeHubService(db).create_collection(payload, owner_id=owner_id)


@router.put("/collections/{collection_id}")
def update_collection(
    collection_id: str,
    payload: KnowledgeCollectionUpdate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).update_collection(collection_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/collections/{collection_id}")
def delete_collection(
    collection_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not KnowledgeHubService(db).delete_collection(collection_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Collection not found.")
    return {"deleted": True}


@router.post("/items/save", status_code=201)
def save_item(
    payload: KnowledgeItemSaveRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).save_item(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/items")
def list_items(
    item_type: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).search_knowledge(
        KnowledgeSearchRequest(item_type=item_type, collection_id=collection_id, tag=tag, limit=limit),
        owner_id=owner_id,
    )


@router.get("/items/{item_id}")
def get_item(item_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).get_item(item_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/items/{item_id}/move")
def move_item(
    item_id: str,
    payload: KnowledgeItemMoveRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).move_item(item_id, payload.collection_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/items/{item_id}")
def delete_item(item_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, bool]:
    if not KnowledgeHubService(db).delete_item(item_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    return {"deleted": True}


@router.post("/search")
def search_knowledge(
    payload: KnowledgeSearchRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).search_knowledge(payload, owner_id=owner_id)


@router.get("/notes")
def list_notes(
    q: str | None = Query(default=None),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).list_notes(owner_id=owner_id, q=q)


@router.post("/notes", status_code=201)
def create_note(
    payload: KnowledgeNoteCreate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).create_note(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/notes/{note_id}")
def update_note(
    note_id: str,
    payload: KnowledgeNoteUpdate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).update_note(note_id, payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, bool]:
    if not KnowledgeHubService(db).delete_note(note_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Note not found.")
    return {"deleted": True}


@router.get("/tags")
def list_tags(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).list_tags(owner_id=owner_id)


@router.put("/tags/{tag_name}")
def rename_tag(
    tag_name: str,
    payload: KnowledgeTagRenameRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        return KnowledgeHubService(db).rename_tag(tag_name, payload.new_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/relationships")
def list_relationships(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).list_relationships(owner_id=owner_id)


@router.post("/relationships", status_code=201)
def create_relationship(
    payload: KnowledgeRelationshipCreate,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).link_items(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/items/{item_id}/recommendations")
def recommend_connections(
    item_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return KnowledgeHubService(db).recommend_connections(item_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/timeline")
def get_timeline(
    category: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return KnowledgeHubService(db).get_timeline(owner_id=owner_id, category=category, limit=limit)


@router.post("/context")
def retrieve_context(
    payload: KnowledgeContextRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return KnowledgeHubService(db).build_knowledge_context(payload, owner_id=owner_id)


@router.post("/import")
def import_knowledge(
    payload: KnowledgeImportRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return KnowledgeHubService(db).import_knowledge(payload, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export")
def export_knowledge(
    format: str = Query(default="json"),
    collection_id: str | None = Query(default=None),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
):
    content, media = KnowledgeHubService(db).export_knowledge(owner_id=owner_id, fmt=format, collection_id=collection_id)
    return Response(content=content, media_type=media)
