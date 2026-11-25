"""SQLAlchemy models for LUMO Phase 11: Knowledge Graph & Entity Intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Entity(Base):
    """Canonical extracted entity representing a person, org, concept, tech, etc."""

    __tablename__ = "entities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True, default="Concept")
    description = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    extraction_method = Column(String(64), nullable=False, default="rule_based")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    aliases = orm_relationship("EntityAlias", back_populates="entity", cascade="all, delete-orphan")
    documents = orm_relationship("EntityDocument", back_populates="entity", cascade="all, delete-orphan")
    outgoing_relationships = orm_relationship(
        "Relationship",
        foreign_keys="Relationship.source_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )
    incoming_relationships = orm_relationship(
        "Relationship",
        foreign_keys="Relationship.target_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("normalized_name", "entity_type", name="uq_entity_normalized_name_type"),
        Index("ix_entities_type_name", "entity_type", "normalized_name"),
    )


class EntityAlias(Base):
    """Known aliases and alternate names resolving to a canonical entity."""

    __tablename__ = "entity_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias = Column(String(255), nullable=False)
    normalized_alias = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    entity = orm_relationship("Entity", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_alias"),
        Index("ix_entity_aliases_norm", "normalized_alias"),
    )


class EntityDocument(Base):
    """Association table linking entities to source documents with mention counts and evidence."""

    __tablename__ = "entity_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mention_count = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=1.0)
    first_snippet = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    entity = orm_relationship("Entity", back_populates="documents")
    document = orm_relationship("Document")

    __table_args__ = (
        UniqueConstraint("entity_id", "document_id", name="uq_entity_document"),
        Index("ix_entity_doc_pair", "entity_id", "document_id"),
    )


class Relationship(Base):
    """Typed relationship between two entities."""

    __tablename__ = "relationships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type = Column(String(64), nullable=False, index=True, default="RELATED_TO")
    confidence = Column(Float, nullable=False, default=1.0)
    extraction_method = Column(String(64), nullable=False, default="rule_based")
    weight = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    source_entity = orm_relationship("Entity", foreign_keys=[source_id], back_populates="outgoing_relationships")
    target_entity = orm_relationship("Entity", foreign_keys=[target_id], back_populates="incoming_relationships")
    evidence = orm_relationship("RelationshipEvidence", back_populates="relationship", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relationship_type", name="uq_relationship_source_target_type"),
        Index("ix_rel_src_tgt", "source_id", "target_id"),
        Index("ix_rel_type", "relationship_type"),
    )


class RelationshipEvidence(Base):
    """Grounded evidence snippet and document supporting a specific relationship."""

    __tablename__ = "relationship_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relationship_id = Column(
        String(36),
        ForeignKey("relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snippet = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    relationship = orm_relationship("Relationship", back_populates="evidence")
    document = orm_relationship("Document")

    __table_args__ = (
        Index("ix_rel_evidence_doc", "relationship_id", "document_id"),
    )


class EntityResolutionLog(Base):
    """Audit log tracking entity merges and resolution history."""

    __tablename__ = "entity_resolution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity_id = Column(String(36), nullable=False, index=True)
    target_entity_id = Column(String(36), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    target_name = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
