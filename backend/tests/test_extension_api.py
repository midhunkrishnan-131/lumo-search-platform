"""Tests for LUMO Phase 15 Browser Companion Extension API endpoints and CORS."""

from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


@pytest.fixture
def ext_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "ext_test.db"
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

    with TestClient(create_app(settings)) as client:
        yield client

    dispose_database()


def test_extension_health_and_cors(ext_client: TestClient):
    resp = ext_client.get(
        "/api/v1/extension/health",
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.headers.get("access-control-allow-origin") == "chrome-extension://abcdefghijklmnop"


def test_extension_save_page_status_duplicate_and_note(ext_client: TestClient):
    # Create a collection first
    col = ext_client.post("/api/v1/workspace/collections", json={"name": "Bookmarks"}).json()

    # Check unsaved page status
    status_before = ext_client.get("/api/v1/extension/status?url=https://example.com/article").json()
    assert status_before["already_saved"] is False
    assert len(status_before["collections"]) == 1

    # Save page with note and tags
    save_resp = ext_client.post(
        "/api/v1/extension/save-page",
        json={
            "url": "https://example.com/article",
            "title": "Example Intelligence Article",
            "description": "Overview of local knowledge graphs.",
            "note": "Read section 3 later.",
            "collection_id": col["id"],
            "tags": ["graph", "reading"],
        },
    )
    assert save_resp.status_code == 201
    data = save_resp.json()
    assert data["is_duplicate"] is False
    assert data["note_id"] is not None
    assert data["item"]["collection_id"] == col["id"]

    # Status now reports already_saved=True
    status_after = ext_client.get("/api/v1/extension/status?url=https://example.com/article").json()
    assert status_after["already_saved"] is True
    assert status_after["item_id"] == data["item"]["id"]

    # Saving same page again detects duplicate
    dup_resp = ext_client.post(
        "/api/v1/extension/save-page",
        json={
            "url": "https://example.com/article",
            "title": "Example Intelligence Article",
            "description": "Overview of local knowledge graphs.",
        },
    )
    assert dup_resp.status_code == 201
    assert dup_resp.json()["is_duplicate"] is True


def test_extension_save_selection_and_search(ext_client: TestClient):
    sel_resp = ext_client.post(
        "/api/v1/extension/save-selection",
        json={
            "url": "https://docs.python.org/3/",
            "title": "Python 3 Documentation",
            "selected_text": "Python is an easy to learn, powerful programming language.",
            "note": "Core Python reference",
            "tags": ["python"],
        },
    )
    assert sel_resp.status_code == 201
    assert sel_resp.json()["item"]["source_type"] == "selection"

    # Search from extension
    search_resp = ext_client.get("/api/v1/extension/search?q=powerful+programming&mode=hybrid")
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] >= 1


def test_extension_rejects_unsafe_url_schemes(ext_client: TestClient):
    for bad_url in ("javascript:alert(1)", "file:///C:/Windows/System32", "chrome://settings"):
        resp = ext_client.post(
            "/api/v1/extension/save-page",
            json={"url": bad_url, "title": "Bad URL"},
        )
        assert resp.status_code == 400
