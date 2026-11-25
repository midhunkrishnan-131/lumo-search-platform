"""Document processing pipeline: extracts, normalizes, deduplicates, and persists documents."""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.processor.extractor import ExtractedDocumentData, extract_document_data

logger = get_logger("processor.pipeline")


def process_document(
    html: str,
    url: str,
    session_id: str | None = None,
    url_id: int | None = None,
    db: Session | None = None,
) -> Document:
    """Process an HTML string, extract metadata, compute hash, deduplicate, and persist.

    Args:
        html: Raw HTML content.
        url: Webpage URL.
        session_id: Optional ID of the crawl session.
        url_id: Optional ID of the crawl URL record.
        db: Optional database Session. When provided, checks deduplication and persists record.

    Returns:
        The Document instance (persisted if db was provided).
    """
    extracted: ExtractedDocumentData = extract_document_data(html, url)

    is_duplicate = False
    primary_doc_id: str | None = None

    if db is not None:
        try:
            # Check for existing document with the identical content_hash
            existing = (
                db.query(Document)
                .filter(Document.content_hash == extracted.content_hash)
                .order_by(Document.created_at.asc())
                .first()
            )

            if existing:
                is_duplicate = True
                # Point to the primary document (original non-duplicate, or existing.id)
                primary_doc_id = existing.primary_document_id or existing.id
                logger.info(
                    "Duplicate document detected for URL %s (matches primary %s)",
                    url,
                    primary_doc_id,
                )
        except Exception as exc:
            logger.warning("Error checking document deduplication: %s", exc)

    doc = Document(
        url_id=url_id,
        session_id=session_id,
        url=url,
        domain=urlparse(url).netloc.lower() or None,
        canonical_url=extracted.canonical_url,
        title=extracted.title,
        description=extracted.description,
        main_content=extracted.main_content,
        headings=extracted.headings,
        language=extracted.language,
        author=extracted.author,
        published_date=extracted.published_date,
        modified_date=extracted.modified_date,
        content_type="text/html",
        content_hash=extracted.content_hash,
        is_duplicate=is_duplicate,
        primary_document_id=primary_doc_id,
        extraction_status=extracted.extraction_status,
        word_count=extracted.word_count,
        error_message=extracted.error_message,
    )

    if db is not None:
        db.add(doc)
        db.flush()

        if not is_duplicate and doc.extraction_status == "completed" and doc.main_content:
            try:
                from app.graph.service import KnowledgeGraphService
                graph_service = KnowledgeGraphService(db)
                graph_service.index_document(doc.id)
            except Exception as graph_err:
                logger.warning("Knowledge Graph indexing deferred for doc %s: %s", doc.id, graph_err)

    return doc
