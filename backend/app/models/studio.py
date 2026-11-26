"""Database models for LUMO Phase 30: Intelligence Studio & Deliverable Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudioProject(Base):
    """Structured Intelligence Studio deliverable project with owner isolation."""

    __tablename__ = "studio_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    title = Column(String(300), nullable=False)
    subtitle = Column(String(500), nullable=True)
    description = Column(Text, nullable=False, default="")
    document_type = Column(String(64), nullable=False, default="research_report", index=True)
    status = Column(String(32), nullable=False, default="draft")
    executive_summary = Column(Text, nullable=False, default="")
    sections_json = Column(JSON, nullable=False, default=list)
    sources_json = Column(JSON, nullable=False, default=list)
    charts_json = Column(JSON, nullable=False, default=list)
    imported_materials_json = Column(JSON, nullable=False, default=dict)
    conclusion = Column(Text, nullable=False, default="")
    version_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    versions = relationship(
        "StudioProjectVersion",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="StudioProjectVersion.version_number.desc()",
    )


class StudioProjectVersion(Base):
    """Immutable version snapshot for a StudioProject."""

    __tablename__ = "studio_project_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36),
        ForeignKey("studio_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    change_summary = Column(String(300), nullable=False, default="Saved snapshot")
    snapshot_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    project = relationship("StudioProject", back_populates="versions")
