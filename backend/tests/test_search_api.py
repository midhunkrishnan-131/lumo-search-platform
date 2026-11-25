"""Integration tests for Search API routes."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.models.history import SearchHistory


@pytest.fixture
def search_api_client(tmp_path):
    db_file = tmp_path / "search_api_test.db"
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

    # Seed test documents
    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            id="doc-search-api-1",
            url="https://architecture.example.com/search-pipelines",
            domain="architecture.example.com",
            title="Search Engine Pipelines and Inverted Indexes",
            description="An overview of inverted index pipelines and scoring algorithms.",
            main_content="Inverted index pipelines mapping terms to postings lists enables ultra-fast keyword lookups.",
            language="en",
            is_duplicate=False,
            content_hash="hash-search-1",
        )
        session.add(doc)
        session.commit()

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

    dispose_database()


def test_search_api_success(search_api_client):
    resp = search_api_client.get("/api/v1/search?q=Pipelines")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "api"
    assert data["query"] == "Pipelines"
    assert data["total"] == 1
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["title"] == "Search Engine Pipelines and Inverted Indexes"
    assert result["domain"] == "architecture.example.com"
    assert "<b>pipelines</b>" in result["snippet"].lower()


def test_search_api_logs_history_automatically(search_api_client):
    # Perform search
    resp = search_api_client.get("/api/v1/search?q=Inverted+index&session_id=sess-123")
    assert resp.status_code == 200

    # Verify search was logged in history
    hist_resp = search_api_client.get("/api/v1/history/search?session_id=sess-123")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 1
    assert hist_data["items"][0]["query"] == "Inverted index"


def test_search_api_respects_privacy_mode(search_api_client):
    # Perform search with privacy=true
    resp = search_api_client.get("/api/v1/search?q=Secret+Query&privacy=true&session_id=sess-private")
    assert resp.status_code == 200

    # Verify search was NOT logged in history
    hist_resp = search_api_client.get("/api/v1/history/search?session_id=sess-private")
    assert hist_resp.status_code == 200
    assert hist_resp.json()["total"] == 0


def test_search_api_respects_privacy_header(search_api_client):
    # Perform search with X-History-Disabled: true
    resp = search_api_client.get(
        "/api/v1/search?q=Header+Secret&session_id=sess-private-2",
        headers={"X-History-Disabled": "true"},
    )
    assert resp.status_code == 200

    hist_resp = search_api_client.get("/api/v1/history/search?session_id=sess-private-2")
    assert hist_resp.status_code == 200
    assert hist_resp.json()["total"] == 0
