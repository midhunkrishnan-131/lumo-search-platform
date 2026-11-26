"""Database model for LUMO Phase 29: Unified Indexing Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.database.connection import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IndexedRecord(Base):
    """Unified index status, fingerprint, and duplicate-detection record."""

    __tablename__ = "indexed_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    source_type = Column(String(48), nullable=False, default="document", index=True)
    source_ref_id = Column(String(64), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    normalized_url = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    shingle_sig = Column(Text, nullable=False, default="")
    chunk_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="indexed", index=True)
    duplicate_of_id = Column(String(36), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
