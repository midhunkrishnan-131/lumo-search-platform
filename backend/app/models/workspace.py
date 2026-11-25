"""SQLAlchemy models for LUMO Phase 14: Personal Intelligence & Knowledge Workspace."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceCollection(Base):
    """User-defined collection for organizing workspace items and notes."""

    __tablename__ = "workspace_collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(160), nullable=False, index=True)
    description = Column(Text, nullable=True)
    parent_id = Column(
        String(36),
        ForeignKey("workspace_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    items = orm_relationship("WorkspaceItem", back_populates="collection")
    notes = orm_relationship("WorkspaceNote", back_populates="collection")


class WorkspaceTag(Base):
    """Normalized tag for categorizing personal items and notes."""

    __tablename__ = "workspace_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, index=True)
    display_name = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class WorkspaceItem(Base):
    """Saved personal knowledge item (web page, PDF, search result, report, entity, bookmark)."""

    __tablename__ = "workspace_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=True)
    source_type = Column(String(48), nullable=False, default="bookmark", index=True)
    source_url = Column(Text, nullable=True)
    source_ref_id = Column(String(64), nullable=True, index=True)
    file_name = Column(String(255), nullable=True)
    file_type = Column(String(32), nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    collection_id = Column(
        String(36),
        ForeignKey("workspace_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_json = Column(JSON, nullable=False, default=dict)
    last_viewed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    collection = orm_relationship("WorkspaceCollection", back_populates="items")
    tag_links = orm_relationship("WorkspaceItemTag", back_populates="item", cascade="all, delete-orphan")
    annotations = orm_relationship("WorkspaceAnnotation", back_populates="item", cascade="all, delete-orphan")
    linked_notes = orm_relationship("WorkspaceNote", back_populates="linked_item")

    __table_args__ = (
        Index("ix_ws_items_type_created", "source_type", "created_at"),
    )


class WorkspaceItemTag(Base):
    """Many-to-many link between WorkspaceItem and WorkspaceTag."""

    __tablename__ = "workspace_item_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("workspace_tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item = orm_relationship("WorkspaceItem", back_populates="tag_links")
    tag = orm_relationship("WorkspaceTag")

    __table_args__ = (
        UniqueConstraint("item_id", "tag_id", name="uq_ws_item_tag"),
    )


class WorkspaceNote(Base):
    """Personal Markdown note linked optionally to collections, items, entities, or research."""

    __tablename__ = "workspace_notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(300), nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    collection_id = Column(
        String(36),
        ForeignKey("workspace_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    linked_item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    linked_entity_id = Column(String(36), nullable=True, index=True)
    linked_research_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    collection = orm_relationship("WorkspaceCollection", back_populates="notes")
    linked_item = orm_relationship("WorkspaceItem", back_populates="linked_notes")
    tag_links = orm_relationship("WorkspaceNoteTag", back_populates="note", cascade="all, delete-orphan")


class WorkspaceNoteTag(Base):
    """Many-to-many link between WorkspaceNote and WorkspaceTag."""

    __tablename__ = "workspace_note_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(
        String(36),
        ForeignKey("workspace_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("workspace_tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    note = orm_relationship("WorkspaceNote", back_populates="tag_links")
    tag = orm_relationship("WorkspaceTag")

    __table_args__ = (
        UniqueConstraint("note_id", "tag_id", name="uq_ws_note_tag"),
    )


class WorkspaceAnnotation(Base):
    """Highlight and user comment anchored to a WorkspaceItem."""

    __tablename__ = "workspace_annotations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = Column(
        String(36),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_text = Column(Text, nullable=False)
    comment = Column(Text, nullable=False, default="")
    start_offset = Column(Integer, nullable=True)
    end_offset = Column(Integer, nullable=True)
    linked_note_id = Column(
        String(36),
        ForeignKey("workspace_notes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    item = orm_relationship("WorkspaceItem", back_populates="annotations")
