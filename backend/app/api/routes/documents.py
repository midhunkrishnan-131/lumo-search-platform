"""FastAPI endpoints for document inspection, retrieval, and processing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.models.crawler import CrawlSession
from app.models.document import Document
from app.processor.pipeline import process_document
from app.schemas.document import (
    DocumentListResponse,
    DocumentMetadataResponse,
    DocumentResponse,
    ProcessDocumentRequest,
)

logger = get_logger("api.documents")

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List processed documents",
    description="Retrieve a paginated list of documents with optional filtering by session, duplication, or status.",
)
def list_documents(
    session_id: Annotated[str | None, Query(description="Filter by crawl session ID")] = None,
    is_duplicate: Annotated[bool | None, Query(description="Filter by duplicate status")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by extraction status")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit")] = 20,
    offset: Annotated[int, Query(ge=0, description="Offset index")] = 0,
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    query = db.query(Document)

    if session_id:
        query = query.filter(Document.session_id == session_id)
    if is_duplicate is not None:
        query = query.filter(Document.is_duplicate == is_duplicate)
    if status_filter:
        query = query.filter(Document.extraction_status == status_filter)

    total = query.count()
    records = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    return DocumentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        documents=[DocumentMetadataResponse.model_validate(r) for r in records],
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get full document by ID",
    description="Retrieve the complete document content, headings, and metadata.",
)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return DocumentResponse.model_validate(doc)


@router.get(
    "/{document_id}/metadata",
    response_model=DocumentMetadataResponse,
    summary="Get document metadata by ID",
    description="Retrieve document metadata without full text payload.",
)
def get_document_metadata(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentMetadataResponse:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return DocumentMetadataResponse.model_validate(doc)


@router.post(
    "/process",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process and persist an HTML document",
    description="Directly parse, clean, normalize, deduplicate, and persist an HTML document.",
)
def process_html_endpoint(
    payload: ProcessDocumentRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    # If session_id provided, ensure session exists
    if payload.session_id:
        sess = db.query(CrawlSession).filter(CrawlSession.id == payload.session_id).first()
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl session '{payload.session_id}' not found",
            )

    doc = process_document(
        html=payload.html,
        url=payload.url,
        session_id=payload.session_id,
        db=db,
    )
    db.commit()
    db.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document and synchronize indexes",
    description="Deletes an indexed document and cleans up its Knowledge Graph associations and vector embeddings.",
)
def delete_document_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
) -> None:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    # 1. Clean up Knowledge Graph associations and orphaned nodes/edges
    try:
        from app.graph.service import KnowledgeGraphService
        KnowledgeGraphService(db).delete_document_entities(document_id)
    except Exception as exc:
        logger.warning("Knowledge Graph cleanup failed for deleted doc %s: %s", document_id, exc)

    # 2. Clean up Semantic Vector Store (best-effort)
    try:
        from app.semantic.vector_store import QdrantVectorStore
        QdrantVectorStore().delete_document_vectors(document_id)
    except Exception as exc:
        logger.debug("Vector store cleanup skipped for deleted doc %s: %s", document_id, exc)

    # 3. Delete Document record
    db.delete(doc)
    db.commit()
