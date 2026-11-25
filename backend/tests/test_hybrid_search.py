"""Tests for Hybrid Search and Reciprocal Rank Fusion (RRF) logic."""

import pytest
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.models.document import Document
from app.search.engine import SearchResult
from app.search.hybrid import HybridSearchOrchestrator, reciprocal_rank_fusion
from app.semantic.indexer import semantic_indexer


def _make_item(doc_id: str, title: str, score: float = 1.0, snippet: str = "") -> SearchResult:
    return SearchResult(
        id=doc_id,
        url=f"https://example.com/{doc_id}",
        title=title,
        domain="example.com",
        description=f"Description for {title}",
        snippet=snippet or f"Snippet for {title}",
        score=score,
    )


def test_rrf_scoring_math():
    """Verify RRF formula 1 / (k + rank) with k=60."""
    k = 60
    # doc 1 is rank 1 in classic, rank 2 in semantic
    # doc 2 is rank 2 in classic, rank 1 in semantic
    # doc 3 is rank 3 in classic only
    # doc 4 is rank 3 in semantic only
    classic = [
        _make_item("1", "Doc 1", score=10.0),
        _make_item("2", "Doc 2", score=5.0),
        _make_item("3", "Doc 3", score=2.0),
    ]
    semantic = [
        _make_item("2", "Doc 2", score=0.9),
        _make_item("1", "Doc 1", score=0.85),
        _make_item("4", "Doc 4", score=0.7),
    ]

    fused = reciprocal_rank_fusion(classic, semantic, k=k)

    assert len(fused) == 4

    # Both doc 1 and doc 2 have ranks 1 and 2:
    # 1 / (60 + 1) + 1 / (60 + 2) = 1/61 + 1/62 = 0.0163934 + 0.0161290 = 0.032522
    expected_top_score = round((1.0 / 61) + (1.0 / 62), 6)
    assert fused[0].hybrid_score == expected_top_score
    assert fused[1].hybrid_score == expected_top_score
    assert set(fused[0].sources) == {"classic", "semantic"}
    assert set(fused[1].sources) == {"classic", "semantic"}

    # doc 3: 1 / (60 + 3) = 1/63 = 0.015873
    doc3 = next(item for item in fused if item.id == "3")
    assert doc3.hybrid_score == round(1.0 / 63, 6)
    assert doc3.sources == ["classic"]
    assert doc3.classic_rank == 3
    assert doc3.semantic_rank is None

    # doc 4: 1 / (60 + 3) = 1/63 = 0.015873
    doc4 = next(item for item in fused if item.id == "4")
    assert doc4.hybrid_score == round(1.0 / 63, 6)
    assert doc4.sources == ["semantic"]
    assert doc4.classic_rank is None
    assert doc4.semantic_rank == 3


def test_rrf_snippet_selection():
    """Verify snippet selection prefers highlighted snippets."""
    classic = [
        _make_item("10", "Python Guide", snippet="A plain overview of Python programming."),
    ]
    semantic = [
        _make_item("10", "Python Guide", snippet="Advanced <b>Python</b> decorators and async."),
    ]

    fused = reciprocal_rank_fusion(classic, semantic, k=60)
    assert len(fused) == 1
    # Highlighted semantic snippet should be preferred
    assert "<b>Python</b>" in fused[0].snippet


@pytest.fixture
def hybrid_db(tmp_path):
    db_file = tmp_path / "hybrid_search_test.db"
    init_database(f"sqlite:///{db_file}")
    create_tables()

    semantic_indexer.store.base_url = "http://127.0.0.1:65530"
    semantic_indexer.store.timeout = 0.2

    session_factory = get_session_factory()
    with session_factory() as session:
        doc1 = Document(
            id="doc-h-1",
            url="https://hybrid.example.org/search-engine",
            domain="hybrid.example.org",
            title="Building High Performance Hybrid Search Engines",
            description="Combining BM25 keyword matching with vector retrieval.",
            main_content="Hybrid search combines lexical full text indexes with dense vector embeddings using Reciprocal Rank Fusion.",
            language="en",
            is_duplicate=False,
            content_hash="hash-h-1",
        )
        session.add(doc1)
        session.commit()

        # Index in semantic indexer
        semantic_indexer.index_document(doc1.id, session)

    yield session_factory
    dispose_database()


def test_hybrid_orchestrator_search(hybrid_db):
    session_factory = hybrid_db
    with session_factory() as session:
        orchestrator = HybridSearchOrchestrator(session, rrf_k=60)

        # Empty query
        empty_res, degraded, meta = orchestrator.search("")
        assert empty_res.total == 0
        assert degraded is False
        assert meta["status"] == "empty_query"

        # Valid query matching indexed doc
        res, degraded, meta = orchestrator.search("hybrid search", page=1, per_page=10)
        assert res.total >= 1
        assert res.results[0].id == "doc-h-1"
        assert res.results[0].hybrid_score is not None
        assert "classic" in res.results[0].sources or "semantic" in res.results[0].sources
        assert meta["fused_total"] >= 1


def test_hybrid_orchestrator_graceful_degradation(hybrid_db, monkeypatch):
    """If semantic search fails with an exception, fallback to classic with degraded=True."""
    session_factory = hybrid_db
    with session_factory() as session:
        orchestrator = HybridSearchOrchestrator(session, rrf_k=60)

        from app.semantic.search import SemanticSearchEngine

        def mock_failing_semantic(*args, **kwargs):
            raise RuntimeError("Simulated Qdrant cluster unavailable")

        monkeypatch.setattr(SemanticSearchEngine, "search", mock_failing_semantic)

        res, degraded, meta = orchestrator.search("hybrid", page=1, per_page=10)
        assert degraded is True
        assert meta["semantic_failed"] is True
        assert meta["classic_failed"] is False
        assert res.total >= 1
