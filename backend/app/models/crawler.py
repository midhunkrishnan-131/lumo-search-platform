"""SQLAlchemy models for web crawling sessions and discovered URLs."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CrawlSession(Base):
    __tablename__ = "crawl_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    max_depth = Column(Integer, nullable=False, default=2)
    max_pages = Column(Integer, nullable=False, default=100)
    crawl_delay = Column(Float, nullable=False, default=1.0)
    pages_crawled = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    urls = relationship(
        "CrawlUrl",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CrawlUrl.id",
    )
    documents = relationship(
        "Document",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Document.created_at",
    )


class CrawlUrl(Base):
    __tablename__ = "crawl_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36),
        ForeignKey("crawl_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=False, index=True)
    depth = Column(Integer, nullable=False, default=0)
    is_seed = Column(Boolean, nullable=False, default=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    http_status = Column(Integer, nullable=True)
    content_type = Column(String(255), nullable=True)
    content_length = Column(Integer, nullable=True)
    title = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    parent_url = Column(Text, nullable=True)
    discovered_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    fetched_at = Column(DateTime(timezone=True), nullable=True)

    session = relationship("CrawlSession", back_populates="urls")
    document = relationship("Document", back_populates="crawl_url", uselist=False)
