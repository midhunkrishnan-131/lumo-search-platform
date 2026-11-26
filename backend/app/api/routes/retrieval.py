"""FastAPI routes for LUMO Phase 29: Advanced Retrieval & Index Management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.retrieval.engine import UnifiedRetrievalEngine
from app.schemas.retrieval import IndexContentRequest, RetrievalSearchRequest

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _resolve_owner(x_lumo_owner: str | None = Header(default=None, alias="X-LUMO-Owner")) -> str:
    cleaned = (x_lumo_owner or "").strip()
    return cleaned[:120] if cleaned else "local"


@router.post("/search")
def retrieval_search(
    payload: RetrievalSearchRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return UnifiedRetrievalEngine(db).retrieve(
        query=payload.query,
        owner_id=owner_id,
        mode=payload.mode,
        limit=payload.limit,
        domain=payload.domain,
        language=payload.language,
        content_type=payload.content_type,
        collection_id=payload.collection_id,
        tag=payload.tag,
        include_knowledge_hub=payload.include_knowledge_hub,
        rerank=payload.rerank,
    )


@router.post("/index", status_code=201)
def index_content(
    payload: IndexContentRequest,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return UnifiedRetrievalEngine(db).index_content(
        title=payload.title,
        content=payload.content,
        source_type=payload.source_type,
        source_ref_id=payload.source_ref_id,
        url=payload.url,
        content_type=payload.content_type,
        metadata=payload.metadata,
        owner_id=owner_id,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )


@router.get("/index/stats")
def index_stats(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    return UnifiedRetrievalEngine(db).get_index_stats(owner_id=owner_id)


@router.get("/index/items")
def list_index_items(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return UnifiedRetrievalEngine(db).list_indexed(owner_id=owner_id, status=status, limit=limit)


@router.post("/index/{record_id}/reindex")
def reindex_item(
    record_id: str,
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return UnifiedRetrievalEngine(db).reindex_record(record_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/index/{record_id}")
def delete_index_item(
    record_id: str,
    confirm: bool = Query(default=False),
    owner_id: str = Depends(_resolve_owner),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    try:
        if not UnifiedRetrievalEngine(db).delete_index_record(record_id, owner_id=owner_id, confirm=confirm):
            raise HTTPException(status_code=404, detail="Indexed record not found.")
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analytics")
def retrieval_analytics(owner_id: str = Depends(_resolve_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    return UnifiedRetrievalEngine(db).get_analytics(owner_id=owner_id)
