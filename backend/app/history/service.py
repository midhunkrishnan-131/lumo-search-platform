"""History and privacy service managing persistent search and browsing events."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.models.history import BrowsingHistory, SearchHistory

logger = get_logger("history.service")


def record_search(
    db: Session,
    query: str,
    mode: str = "classic",
    total_results: int = 0,
    filters: dict | None = None,
    session_id: str | None = None,
    privacy_disabled: bool = False,
) -> SearchHistory | None:
    """Record a user search query in history if privacy mode is not active."""
    if privacy_disabled:
        logger.debug("Search history logging bypassed due to privacy settings.")
        return None

    clean_query = query.strip()
    if not clean_query:
        return None

    try:
        rec = SearchHistory(
            query=clean_query,
            mode=mode,
            filters=filters or {},
            total_results=total_results,
            session_id=session_id,
        )
        db.add(rec)
        db.flush()
        return rec
    except Exception as exc:
        logger.warning("Failed to record search history: %s", exc)
        return None


def list_search_history(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    session_id: str | None = None,
) -> tuple[int, list[SearchHistory]]:
    """Retrieve paginated search history."""
    query = db.query(SearchHistory)
    if session_id:
        query = query.filter(SearchHistory.session_id == session_id)

    total = query.count()
    records = query.order_by(SearchHistory.created_at.desc()).offset(offset).limit(limit).all()
    return total, records


def delete_search_history_item(db: Session, item_id: str) -> bool:
    """Delete a single search history entry."""
    rec = db.query(SearchHistory).filter(SearchHistory.id == item_id).first()
    if not rec:
        return False
    db.delete(rec)
    db.commit()
    return True


def clear_search_history(db: Session, session_id: str | None = None) -> int:
    """Clear all or session-scoped search history."""
    query = db.query(SearchHistory)
    if session_id:
        query = query.filter(SearchHistory.session_id == session_id)
    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return deleted_count


def record_browsing(
    db: Session,
    url: str,
    title: str | None = None,
    document_id: str | None = None,
    session_id: str | None = None,
    dwell_seconds: int = 0,
    referrer: str | None = None,
    privacy_disabled: bool = False,
) -> BrowsingHistory | None:
    """Record a webpage visit or result click in browsing history."""
    if privacy_disabled:
        logger.debug("Browsing history logging bypassed due to privacy settings.")
        return None

    clean_url = url.strip()
    if not clean_url:
        return None

    domain_val = urlparse(clean_url).netloc.lower() or None

    # Link to Document if document_id not provided
    if not document_id:
        doc = db.query(Document).filter(Document.url == clean_url).first()
        if doc:
            document_id = doc.id
            title = title or doc.title

    try:
        rec = BrowsingHistory(
            document_id=document_id,
            url=clean_url,
            title=title or clean_url,
            domain=domain_val,
            session_id=session_id,
            dwell_seconds=max(0, dwell_seconds),
            referrer=referrer,
        )
        db.add(rec)
        db.flush()
        return rec
    except Exception as exc:
        logger.warning("Failed to record browsing history: %s", exc)
        return None


def list_browsing_history(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    session_id: str | None = None,
) -> tuple[int, list[BrowsingHistory]]:
    """Retrieve paginated browsing history."""
    query = db.query(BrowsingHistory)
    if session_id:
        query = query.filter(BrowsingHistory.session_id == session_id)

    total = query.count()
    records = query.order_by(BrowsingHistory.visited_at.desc()).offset(offset).limit(limit).all()
    return total, records


def delete_browsing_history_item(db: Session, item_id: str) -> bool:
    """Delete a single browsing history entry."""
    rec = db.query(BrowsingHistory).filter(BrowsingHistory.id == item_id).first()
    if not rec:
        return False
    db.delete(rec)
    db.commit()
    return True


def clear_browsing_history(db: Session, session_id: str | None = None) -> int:
    """Clear all or session-scoped browsing history."""
    query = db.query(BrowsingHistory)
    if session_id:
        query = query.filter(BrowsingHistory.session_id == session_id)
    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return deleted_count


def export_history(db: Session, session_id: str | None = None) -> dict:
    """Export complete search and browsing history as structured JSON."""
    _, searches = list_search_history(db, limit=1000, session_id=session_id)
    _, visits = list_browsing_history(db, limit=1000, session_id=session_id)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_searches": len(searches),
        "total_visits": len(visits),
        "search_history": [
            {
                "id": s.id,
                "query": s.query,
                "mode": s.mode,
                "filters": s.filters,
                "total_results": s.total_results,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in searches
        ],
        "browsing_history": [
            {
                "id": b.id,
                "document_id": b.document_id,
                "url": b.url,
                "title": b.title,
                "domain": b.domain,
                "visited_at": b.visited_at.isoformat() if b.visited_at else None,
                "dwell_seconds": b.dwell_seconds,
                "referrer": b.referrer,
            }
            for b in visits
        ],
    }
