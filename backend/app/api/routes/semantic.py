"""FastAPI endpoints for Semantic Search and vector index management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.history.service import record_search
from app.models.document import Document
from app.schemas.search import SearchResponse, SearchResultItem
from app.schemas.semantic import (
    BatchIndexResponse,
    DocumentSemanticStatus,
    SemanticIndexStatusResponse,
)
from app.semantic.embedding import embedding_service
from app.semantic.indexer import semantic_indexer
from app.semantic.search import SemanticSearchEngine
from app.semantic.vector_store import vector_store

logger = get_logger("api.semantic")

router = APIRouter(prefix="/semantic", tags=["semantic"])


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Semantic vector search",
    description="Contextual and semantic similarity search across indexed document vector embeddings.",
)
def semantic_search_endpoint(
    q: Annotated[str, Query(max_length=400, description="Semantic search query")] = "",
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page")] = 8,
    domain: Annotated[str | None, Query(description="Domain filter")] = None,
    language: Annotated[str | None, Query(description="Language filter")] = None,
    session_id: Annotated[str | None, Query(description="Optional client session ID")] = None,
    privacy: Annotated[bool, Query(description="When True, prevents search history logging")] = False,
    x_history_disabled: Annotated[bool, Header(alias="X-History-Disabled")] = False,
    db: Session = Depends(get_db),
) -> SearchResponse:
    engine = SemanticSearchEngine(db=db, vector_store=vector_store, embedder=embedding_service)
    search_set = engine.search(
        query=q,
        page=page,
        per_page=per_page,
        domain=domain,
        language=language,
    )

    # Log search history
    privacy_active = privacy or x_history_disabled
    if q.strip():
        try:
            filters = {}
            if domain:
                filters["domain"] = domain
            if language:
                filters["language"] = language

            record_search(
                db=db,
                query=q,
                mode="semantic",
                total_results=search_set.total,
                filters=filters,
                session_id=session_id,
                privacy_disabled=privacy_active,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Could not persist semantic search history: %s", exc)

    return SearchResponse(
        source="api",
        query=search_set.query,
        mode="semantic",
        total=search_set.total,
        page=search_set.page,
        per_page=search_set.per_page,
        total_pages=search_set.total_pages,
        results=[SearchResultItem.model_validate(r) for r in search_set.results],
    )


@router.post(
    "/index/{document_id}",
    response_model=DocumentSemanticStatus,
    summary="Index document vectors",
    description="Chunks and generates vector embeddings for a specific document into Qdrant.",
)
def index_document_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentSemanticStatus:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    ok = semantic_indexer.index_document(document_id, db)
    db.refresh(doc)
    return DocumentSemanticStatus(
        document_id=doc.id,
        semantic_status=doc.semantic_status,
        indexed_chunks_count=doc.indexed_chunks_count,
        semantic_indexed_at=doc.semantic_indexed_at,
        semantic_error=doc.semantic_error,
    )


@router.post(
    "/reindex/{document_id}",
    response_model=DocumentSemanticStatus,
    summary="Reindex document vectors",
    description="Deletes old vectors and regenerates embeddings for a document.",
)
def reindex_document_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentSemanticStatus:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    semantic_indexer.reindex_document(document_id, db)
    db.refresh(doc)
    return DocumentSemanticStatus(
        document_id=doc.id,
        semantic_status=doc.semantic_status,
        indexed_chunks_count=doc.indexed_chunks_count,
        semantic_indexed_at=doc.semantic_indexed_at,
        semantic_error=doc.semantic_error,
    )


@router.get(
    "/index/status",
    response_model=SemanticIndexStatusResponse,
    summary="Get semantic indexing status",
    description="Returns aggregate vector statistics, embedding model details, and Qdrant health.",
)
def get_semantic_status(
    db: Session = Depends(get_db),
) -> SemanticIndexStatusResponse:
    total_docs = db.query(Document).filter(Document.is_duplicate.is_(False)).count()
    indexed_docs = db.query(Document).filter(Document.semantic_status == "indexed").count()
    pending_docs = db.query(Document).filter(Document.semantic_status == "pending", Document.is_duplicate.is_(False)).count()
    failed_docs = db.query(Document).filter(Document.semantic_status == "failed").count()

    model_diag = embedding_service.get_status()
    total_vectors = vector_store.count_vectors()
    is_qdrant_live = vector_store.is_qdrant_available()

    return SemanticIndexStatusResponse(
        total_documents=total_docs,
        indexed_documents=indexed_docs,
        pending_documents=pending_docs,
        failed_documents=failed_docs,
        total_vectors=total_vectors,
        embedding_backend=model_diag.get("backend", "unknown"),
        model_name=embedding_service.model_name,
        dimension=embedding_service.dimension,
        is_qdrant_live=is_qdrant_live,
    )


@router.get(
    "/index/{document_id}",
    response_model=DocumentSemanticStatus,
    summary="Get document semantic index status",
)
def get_document_semantic_status(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentSemanticStatus:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return DocumentSemanticStatus(
        document_id=doc.id,
        semantic_status=doc.semantic_status,
        indexed_chunks_count=doc.indexed_chunks_count,
        semantic_indexed_at=doc.semantic_indexed_at,
        semantic_error=doc.semantic_error,
    )


@router.post(
    "/index/pending",
    response_model=BatchIndexResponse,
    summary="Batch index pending documents",
    description="Index pending non-duplicate documents into vector storage.",
)
def batch_index_pending(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> BatchIndexResponse:
    indexed = semantic_indexer.index_pending_documents(db=db, limit=limit)
    return BatchIndexResponse(requested=limit, indexed_count=indexed)
