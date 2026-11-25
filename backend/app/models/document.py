"""SQLAlchemy model for extracted and processed documents."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
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


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url_id = Column(
        Integer,
        ForeignKey("crawl_urls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id = Column(
        String(36),
        ForeignKey("crawl_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=True, index=True)
    canonical_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    main_content = Column(Text, nullable=False, default="")
    headings = Column(JSON, nullable=False, default=list)
    language = Column(String(16), nullable=True)
    author = Column(String(255), nullable=True)
    published_date = Column(String(64), nullable=True)
    modified_date = Column(String(64), nullable=True)
    content_type = Column(String(128), nullable=False, default="text/html")
    content_hash = Column(String(64), nullable=False, index=True)
    is_duplicate = Column(Boolean, nullable=False, default=False, index=True)
    primary_document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extraction_status = Column(
        String(32),
        nullable=False,
        default="completed",
        index=True,
    )
    semantic_status = Column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    indexed_chunks_count = Column(Integer, nullable=False, default=0)
    semantic_indexed_at = Column(DateTime(timezone=True), nullable=True)
    semantic_error = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    crawl_url = relationship("CrawlUrl", back_populates="document")
    session = relationship("CrawlSession", back_populates="documents")
    primary_document = relationship(
        "Document",
        remote_side=[id],
        backref="duplicates",
        foreign_keys=[primary_document_id],
    )
