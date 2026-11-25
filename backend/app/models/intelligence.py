"""SQLAlchemy models for LUMO Phase 18: Universal Data Intelligence Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UniversalDataset(Base):
    """Structured dataset metadata, schema profile, and data quality summary."""

    __tablename__ = "universal_datasets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title = Column(String(500), nullable=False, index=True)
    file_name = Column(String(255), nullable=True)
    file_type = Column(String(24), nullable=False, index=True)  # csv | xlsx | json | jsonl
    row_count = Column(Integer, nullable=False, default=0)
    column_count = Column(Integer, nullable=False, default=0)
    sheet_count = Column(Integer, nullable=False, default=1)
    sheet_names = Column(JSON, nullable=False, default=list)
    active_sheet = Column(String(160), nullable=True)
    columns_json = Column(JSON, nullable=False, default=list)
    profile_json = Column(JSON, nullable=False, default=dict)
    summary = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    import_jobs = orm_relationship("UniversalImportJob", back_populates="dataset")


class UniversalImportJob(Base):
    """Persistent state machine for Universal Data Ingestion & Processing Pipeline."""

    __tablename__ = "universal_import_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_kind = Column(String(32), nullable=False, default="file", index=True)  # file | url | workspace
    format_type = Column(String(32), nullable=False, default="unknown", index=True)
    content_category = Column(String(64), nullable=False, default="general_document", index=True)
    file_name = Column(String(255), nullable=True)
    source_url = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    current_stage = Column(String(48), nullable=False, default="queued")
    progress_pct = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    workspace_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id = Column(
        String(36),
        ForeignKey("universal_datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    dataset = orm_relationship("UniversalDataset", back_populates="import_jobs")

    __table_args__ = (
        Index("ix_uni_jobs_status_created", "status", "created_at"),
    )


class UniversalAnalysisReport(Base):
    """Persisted document, dataset, comparison, and cross-document intelligence reports."""

    __tablename__ = "universal_analysis_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type = Column(String(48), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    question = Column(Text, nullable=True)
    summary = Column(Text, nullable=False, default="")
    result_json = Column(JSON, nullable=False, default=dict)
    source_ids = Column(JSON, nullable=False, default=list)
    provider = Column(String(48), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
