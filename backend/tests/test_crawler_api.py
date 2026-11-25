"""Integration tests for crawler API routes."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


@pytest.fixture
def crawler_client(tmp_path):
    db_file = tmp_path / "crawler_test.db"
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


def test_create_session_with_valid_seeds(crawler_client):
    response = crawler_client.post(
        "/api/v1/crawler/sessions",
        json={
            "seed_urls": ["https://8.8.8.8/", "https://1.1.1.1/docs"],
            "name": "Integration Test Crawl",
            "max_depth": 2,
            "max_pages": 10,
            "crawl_delay": 0.5,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Integration Test Crawl"
    assert data["status"] == "pending"
    assert data["max_depth"] == 2
    assert data["max_pages"] == 10
    assert data["seeds_count"] == 2
    assert data["queued_count"] == 2


def test_create_session_rejects_ssrf_seeds(crawler_client):
    response = crawler_client.post(
        "/api/v1/crawler/sessions",
        json={
            "seed_urls": ["http://127.0.0.1/admin"],
            "name": "Malicious Seed Attempt",
        },
    )
    assert response.status_code == 400
    assert "Invalid seed URL" in response.json()["detail"]


def test_create_session_rejects_invalid_scheme(crawler_client):
    response = crawler_client.post(
        "/api/v1/crawler/sessions",
        json={
            "seed_urls": ["ftp://example.com/files"],
        },
    )
    assert response.status_code == 400
    assert "Unsupported scheme" in response.json()["detail"]


def test_get_session_and_list_urls(crawler_client):
    # 1. Create session
    create_res = crawler_client.post(
        "/api/v1/crawler/sessions",
        json={
            "seed_urls": ["https://8.8.8.8/"],
            "name": "Query Test",
        },
    )
    session_id = create_res.json()["id"]

    # 2. Get session by ID
    get_res = crawler_client.get(f"/api/v1/crawler/sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == session_id
    assert get_res.json()["seeds_count"] == 1

    # 3. List URLs
    urls_res = crawler_client.get(f"/api/v1/crawler/sessions/{session_id}/urls")
    assert urls_res.status_code == 200
    urls_data = urls_res.json()
    assert urls_data["total"] == 1
    assert urls_data["urls"][0]["url"] == "https://8.8.8.8/"
    assert urls_data["urls"][0]["is_seed"] is True
    assert urls_data["urls"][0]["status"] == "queued"


def test_list_sessions(crawler_client):
    for i in range(3):
        crawler_client.post(
            "/api/v1/crawler/sessions",
            json={
                "seed_urls": [f"https://8.8.8.8/{i}"],
                "name": f"Session {i}",
            },
        )

    list_res = crawler_client.get("/api/v1/crawler/sessions")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 3
    assert len(data["sessions"]) >= 3


def test_stop_session(crawler_client):
    create_res = crawler_client.post(
        "/api/v1/crawler/sessions",
        json={
            "seed_urls": ["https://8.8.8.8/"],
            "name": "Stop Session Test",
        },
    )
    session_id = create_res.json()["id"]

    stop_res = crawler_client.post(f"/api/v1/crawler/sessions/{session_id}/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["id"] == session_id


def test_get_nonexistent_session_returns_404(crawler_client):
    res = crawler_client.get("/api/v1/crawler/sessions/nonexistent-id")
    assert res.status_code == 404
    assert res.json()["detail"] == "Crawl session not found."
