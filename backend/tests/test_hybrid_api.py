"""Integration tests for Hybrid Search API endpoints and history recording."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.models.history import SearchHistory
from app.semantic.indexer import semantic_indexer


@pytest.fixture
def hybrid_api_client(tmp_path):
    db_file = tmp_path / "hybrid_api_test.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="http://localhost:3000,http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    semantic_indexer.store.base_url = "http://127.0.0.1:65530"
    semantic_indexer.store.timeout = 0.2
    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            id="doc-api-hybrid-1",
            url="https://hybrid.example.com/vector-fusion",
            domain="hybrid.example.com",
            title="Reciprocal Rank Fusion in Modern Search Engines",
            description="Fusing dense semantic representations with inverted keyword indices.",
            main_content="Reciprocal Rank Fusion combines ranked lists by awarding 1 / (k + rank) to each candidate document.",
            language="en",
            is_duplicate=False,
            content_hash="hash-hybrid-api-1",
        )
        session.add(doc)
        session.commit()

        semantic_indexer.index_document(doc.id, session)

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, session_factory

    dispose_database()


def test_hybrid_search_dedicated_endpoint(hybrid_api_client):
    client, _ = hybrid_api_client
    resp = client.get("/api/v1/search/hybrid?q=reciprocal%20rank&per_page=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "reciprocal rank"
    assert data["mode"] == "hybrid"
    assert "degraded" in data
    assert data["degraded"] is False
    assert len(data["results"]) >= 1
    top_result = data["results"][0]
    assert "sources" in top_result
    assert "hybrid_score" in top_result
    assert top_result["hybrid_score"] > 0


def test_search_unified_endpoint_routing(hybrid_api_client):
    client, session_factory = hybrid_api_client
    resp = client.get("/api/v1/search?q=fusion&mode=hybrid")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "fusion"
    assert data["mode"] == "hybrid"
    assert "execution_metadata" in data

    # Verify history is logged
    with session_factory() as session:
        entry = session.execute(
            select(SearchHistory).where(SearchHistory.query == "fusion")
        ).scalars().first()
        assert entry is not None
        assert entry.mode == "hybrid"


def test_hybrid_search_privacy_mode(hybrid_api_client):
    client, session_factory = hybrid_api_client
    resp = client.get(
        "/api/v1/search/hybrid?q=private_hybrid_query&privacy=true",
        headers={"X-History-Disabled": "true"},
    )
    assert resp.status_code == 200

    with session_factory() as session:
        entry = session.execute(
            select(SearchHistory).where(SearchHistory.query == "private_hybrid_query")
        ).scalars().first()
        assert entry is None
