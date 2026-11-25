"""Integration tests for Semantic Search API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.semantic.indexer import semantic_indexer


@pytest.fixture
def semantic_api_client(tmp_path):
    db_file = tmp_path / "semantic_api_test.db"
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

    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            id="doc-api-sem-1",
            url="https://robotics.example.com/kinematics",
            domain="robotics.example.com",
            title="Robotic Kinematics and Inverse Solvers",
            description="Mathematical formulations for forward and inverse kinematic chains.",
            main_content="Inverse kinematics computes joint angles needed to position an end effector at target coordinates.",
            language="en",
            is_duplicate=False,
            content_hash="hash-kinematics-1",
        )
        session.add(doc)
        session.commit()

        semantic_indexer.index_document(doc.id, session)

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

    dispose_database()


def test_semantic_status_endpoint(semantic_api_client):
    resp = semantic_api_client.get("/api/v1/semantic/index/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] >= 1
    assert data["indexed_documents"] >= 1
    assert data["dimension"] == 384


def test_semantic_search_dedicated_endpoint(semantic_api_client):
    resp = semantic_api_client.get("/api/v1/semantic/search?q=Inverse+kinematics+effector")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "semantic"
    assert data["total"] >= 1
    assert data["results"][0]["title"] == "Robotic Kinematics and Inverse Solvers"


def test_search_endpoint_with_mode_semantic(semantic_api_client):
    # Verify GET /api/v1/search?q=...&mode=semantic (called by frontend searchSemantic)
    resp = semantic_api_client.get("/api/v1/search?q=Inverse+kinematics&mode=semantic")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "semantic"
    assert data["total"] >= 1
    assert data["results"][0]["id"] == "doc-api-sem-1"

    # Verify search history recorded with mode='semantic'
    hist_resp = semantic_api_client.get("/api/v1/history/search")
    assert hist_resp.status_code == 200
    assert any(h["mode"] == "semantic" for h in hist_resp.json()["items"])
