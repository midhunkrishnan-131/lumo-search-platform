"""Tests for KnowledgeGraphService document indexing and deletion synchronization."""

from collections.abc import Generator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.graph.service import KnowledgeGraphService
from app.models.document import Document
from app.models.graph import (
    Entity,
    EntityDocument,
    Relationship,
    RelationshipEvidence,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_index_document_creates_entities_and_relationships(db_session: Session):
    doc = Document(
        id="doc-test-1",
        url="https://example.com/search-architecture",
        title="LUMO Hybrid Search Architecture",
        main_content=(
            "FastAPI is a Python web framework. "
            "LUMO uses Hybrid Search combining BM25 and Semantic Retrieval. "
            "FastAPI routes search queries cleanly."
        ),
        content_hash="test-hash-1",
        extraction_status="completed",
        is_duplicate=False,
    )
    db_session.add(doc)
    db_session.commit()

    service = KnowledgeGraphService(db_session)
    ent_count, rel_count = service.index_document(doc.id)

    assert ent_count > 0
    # Check entities in database
    entities = db_session.query(Entity).all()
    assert len(entities) >= 3

    # Check entity document association
    ent_docs = db_session.query(EntityDocument).filter(EntityDocument.document_id == doc.id).all()
    assert len(ent_docs) == len(entities)

    # Check overview
    overview = service.get_overview()
    assert len(overview.nodes) >= 3
    assert overview.total_nodes >= 3


def test_delete_document_cleans_up_orphaned_entities_and_relationships(db_session: Session):
    doc = Document(
        id="doc-orphan-1",
        url="https://example.com/unique-article",
        title="Unique Isolated Article",
        main_content="Qdrant integrates with PostgreSQL for vector storage.",
        content_hash="orphan-hash-1",
        extraction_status="completed",
        is_duplicate=False,
    )
    db_session.add(doc)
    db_session.commit()

    service = KnowledgeGraphService(db_session)
    service.index_document(doc.id)

    assert db_session.query(Entity).count() > 0

    # Delete document associations
    service.delete_document_entities(doc.id)

    # Orphaned entities and relations should be cleaned up
    assert db_session.query(EntityDocument).filter(EntityDocument.document_id == doc.id).count() == 0
    assert db_session.query(Entity).count() == 0


def test_reprocess_all_documents(db_session: Session):
    doc = Document(
        id="doc-reprocess-1",
        url="https://example.com/reprocess",
        title="Reprocessing Document",
        main_content="Python is used by FastAPI.",
        content_hash="rep-hash-1",
        extraction_status="completed",
        is_duplicate=False,
    )
    db_session.add(doc)
    db_session.commit()

    service = KnowledgeGraphService(db_session)
    result = service.reprocess_all(batch_size=10)

    assert result["status"] == "completed"
    assert result["documents_processed"] == 1
    assert result["entities_extracted"] > 0
