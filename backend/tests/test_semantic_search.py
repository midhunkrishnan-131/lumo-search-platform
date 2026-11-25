"""Integration tests for Semantic Indexing and Document-Level Aggregated Search."""

import pytest
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.models.document import Document
from app.semantic.embedding import LocalEmbeddingService
from app.semantic.indexer import SemanticIndexer
from app.semantic.search import SemanticSearchEngine
from app.semantic.vector_store import QdrantVectorStore


@pytest.fixture
def semantic_env(tmp_path):
    db_file = tmp_path / "semantic_search_test.db"
    init_database(f"sqlite:///{db_file}")
    create_tables()

    storage_path = tmp_path / "semantic_qdrant_store"
    store = QdrantVectorStore(
        base_url="http://127.0.0.1:65530",
        collection_name="sem_test",
        storage_path=str(storage_path),
        dimension=384,
    )
    embedder = LocalEmbeddingService(dimension=384)
    indexer = SemanticIndexer(vector_store=store, embedder=embedder)

    session_factory = get_session_factory()
    with session_factory() as session:
        # Seed 2 documents: doc1 has multiple paragraphs about Machine Learning
        doc1 = Document(
            id="doc-sem-1",
            url="https://ml.example.org/foundations",
            domain="ml.example.org",
            title="Foundations of Machine Learning",
            description="A comprehensive guide to neural networks and backpropagation.",
            main_content=(
                "Machine learning models optimize loss functions using gradient descent.\n\n"
                "Deep learning uses multilayer perceptrons and convolutional layers for vision.\n\n"
                "Transformers employ self-attention mechanisms to process sequential tokens."
            ),
            language="en",
            is_duplicate=False,
            content_hash="hash-sem-1",
        )
        doc2 = Document(
            id="doc-sem-2",
            url="https://gardening.example.org/soil-prep",
            domain="gardening.example.org",
            title="Organic Gardening and Soil Preparation",
            description="Tips for compost, nitrogen enrichment, and crop rotation.",
            main_content="Healthy garden soil requires organic matter, earthworms, and appropriate moisture levels for root development.",
            language="en",
            is_duplicate=False,
            content_hash="hash-sem-2",
        )
        session.add_all([doc1, doc2])
        session.commit()

        # Index both documents
        indexer.index_document("doc-sem-1", session)
        indexer.index_document("doc-sem-2", session)

        yield session, store, embedder

    dispose_database()


def test_semantic_search_and_document_aggregation(semantic_env):
    session, store, embedder = semantic_env
    engine = SemanticSearchEngine(db=session, vector_store=store, embedder=embedder)

    # Search for ML concepts
    res = engine.search("neural networks gradient descent", page=1, per_page=10)
    assert res.total >= 1
    # doc-sem-1 must be the top result
    top = res.results[0]
    assert top.id == "doc-sem-1"
    assert top.title == "Foundations of Machine Learning"
    assert top.domain == "ml.example.org"
    assert top.score > 0.0
    # Multiple chunks should NOT produce duplicate search results for doc1
    doc_ids = [r.id for r in res.results]
    assert doc_ids.count("doc-sem-1") == 1


def test_semantic_search_domain_filter(semantic_env):
    session, store, embedder = semantic_env
    engine = SemanticSearchEngine(db=session, vector_store=store, embedder=embedder)

    res = engine.search("soil garden compost", domain="gardening.example.org")
    assert res.total == 1
    assert res.results[0].id == "doc-sem-2"
