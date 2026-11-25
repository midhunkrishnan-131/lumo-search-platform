"""SQLAlchemy models for LUMO Phase 22: External Integration Layer."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationRecord(Base):
    """Registered external integration with configuration, permissions, and sync state."""

    __tablename__ = "integrations"

    id = Column(String(64), primary_key=True)
    name = Column(String(160), nullable=False)
    category = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    version = Column(String(32), nullable=False, default="1.0.0")
    enabled = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String(32), nullable=False, default="not_configured", index=True)
    connection_status = Column(String(32), nullable=False, default="unknown")
    permissions_json = Column(JSON, nullable=False, default=list)
    config_json = Column(JSON, nullable=False, default=dict)
    has_secret = Column(Boolean, nullable=False, default=False)
    secret_encrypted = Column(Text, nullable=True)
    sync_frequency_minutes = Column(Integer, nullable=False, default=60)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    sources = orm_relationship("IntegrationSource", back_populates="integration", cascade="all, delete-orphan")
    sync_runs = orm_relationship("IntegrationSyncRun", back_populates="integration", cascade="all, delete-orphan")
    import_records = orm_relationship("IntegrationImportRecord", back_populates="integration", cascade="all, delete-orphan")


class IntegrationSource(Base):
    """Monitored external source (RSS feed, GitHub repo, docs URL, dataset, API endpoint)."""

    __tablename__ = "integration_sources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(240), nullable=False)
    source_url = Column(Text, nullable=False)
    source_type = Column(String(48), nullable=False, default="feed")
    monitored = Column(Boolean, nullable=False, default=True, index=True)
    paused = Column(Boolean, nullable=False, default=False, index=True)
    sync_frequency_minutes = Column(Integer, nullable=False, default=60)
    last_item_hash = Column(String(64), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    config_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    integration = orm_relationship("IntegrationRecord", back_populates="sources")


class IntegrationSyncRun(Base):
    """Execution history and metrics for an integration synchronization run."""

    __tablename__ = "integration_sync_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(
        String(36),
        ForeignKey("integration_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger_mode = Column(String(32), nullable=False, default="manual")
    status = Column(String(32), nullable=False, default="running", index=True)
    imported_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    integration = orm_relationship("IntegrationRecord", back_populates="sync_runs")

    __table_args__ = (
        Index("ix_int_sync_int_started", "integration_id", "started_at"),
    )


class IntegrationImportRecord(Base):
    """Deduplication and provenance record for imported external items."""

    __tablename__ = "integration_import_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(
        String(36),
        ForeignKey("integration_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_id = Column(String(255), nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    url = Column(Text, nullable=True)
    workspace_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    integration = orm_relationship("IntegrationRecord", back_populates="import_records")

    __table_args__ = (
        UniqueConstraint("integration_id", "content_hash", name="uq_int_import_hash"),
    )
