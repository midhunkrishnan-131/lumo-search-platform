"""SQLAlchemy models for persistent search and browsing history."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    query = Column(Text, nullable=False, index=True)
    mode = Column(String(32), nullable=False, default="classic")
    filters = Column(JSON, nullable=False, default=dict)
    total_results = Column(Integer, nullable=False, default=0)
    session_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class BrowsingHistory(Base):
    __tablename__ = "browsing_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    domain = Column(String(255), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    visited_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    dwell_seconds = Column(Integer, nullable=False, default=0)
    referrer = Column(Text, nullable=True)

    # Relationships
    document = relationship("Document", backref="browsing_events")
