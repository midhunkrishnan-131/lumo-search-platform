"""Database models for LUMO Phase 28: Personal Knowledge Hub & Persistent Intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text

from app.database.connection import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


VALID_KNOWLEDGE_ITEM_TYPES = {
    "SEARCH_RESULT",
    "SOURCE",
    "RESEARCH_REPORT",
    "AI_ANSWER",
    "DOCUMENT",
    "DATASET",
    "DATA_ANALYSIS",
    "GRAPH_ENTITY",
    "GRAPH_RELATIONSHIP",
    "WORKFLOW_RESULT",
    "NOTE",
}


class KnowledgeItemMeta(Base):
    """Owner isolation, Phase 28 item_type, provenance, and related references for WorkspaceItem."""

    __tablename__ = "knowledge_item_meta"

    item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    item_type = Column(String(48), nullable=False, default="SOURCE", index=True)
    provenance_json = Column(JSON, nullable=False, default=dict)
    related_refs_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)


class KnowledgeCollectionMeta(Base):
    """Owner isolation, icon, and tags metadata for WorkspaceCollection."""

    __tablename__ = "knowledge_collection_meta"

    collection_id = Column(
        String(36),
        ForeignKey("workspace_collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    icon = Column(String(32), nullable=False, default="folder")
    tags_json = Column(JSON, nullable=False, default=list)


class KnowledgeRelationship(Base):
    """Traceable relationship between Knowledge Hub items."""

    __tablename__ = "knowledge_relationships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    source_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type = Column(String(64), nullable=False, default="RELATES_TO")
    evidence = Column(Text, nullable=False, default="")
    is_inferred = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)


class KnowledgeActivity(Base):
    """Persistent timeline activity log for Knowledge Hub operations."""

    __tablename__ = "knowledge_activities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    category = Column(String(48), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
