"""Tests for Document API routes."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


@pytest.fixture
def doc_client(tmp_path):
    db_file = tmp_path / "doc_api_test.db"
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

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

    dispose_database()


def test_process_and_retrieve_document(doc_client):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Quantum Computing Primer</title>
        <meta name="description" content="Introduction to qubits and superposition.">
    </head>
    <body>
        <article>
            <h1>Quantum Computing Primer</h1>
            <p>Quantum computers exploit superposition and entanglement to solve specific problems.</p>
        </article>
    </body>
    </html>
    """

    # 1. Process document via API
    resp = doc_client.post(
        "/api/v1/documents/process",
        json={"url": "https://example.org/quantum", "html": html},
    )
    assert resp.status_code == 201
    created = resp.json()
    doc_id = created["id"]
    assert created["title"] == "Quantum Computing Primer"
    assert created["word_count"] > 5
    assert not created["is_duplicate"]
    assert "superposition" in created["main_content"]

    # 2. Get full document
    get_resp = doc_client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == doc_id
    assert get_resp.json()["main_content"] == created["main_content"]

    # 3. Get metadata
    meta_resp = doc_client.get(f"/api/v1/documents/{doc_id}/metadata")
    assert meta_resp.status_code == 200
    assert "main_content" not in meta_resp.json()
    assert meta_resp.json()["title"] == "Quantum Computing Primer"

    # 4. List documents
    list_resp = doc_client.get("/api/v1/documents")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(d["id"] == doc_id for d in list_data["documents"])


def test_get_nonexistent_document(doc_client):
    resp = doc_client.get("/api/v1/documents/invalid-uuid-1234")
    assert resp.status_code == 404
