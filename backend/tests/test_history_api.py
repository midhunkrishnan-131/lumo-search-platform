"""Integration tests for Persistent History and Privacy API routes."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


@pytest.fixture
def history_client(tmp_path):
    db_file = tmp_path / "history_api_test.db"
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


def test_browsing_history_lifecycle(history_client):
    # 1. Record browse event
    browse_payload = {
        "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP",
        "title": "HTTP | MDN",
        "dwell_seconds": 45,
        "session_id": "test-session-history",
    }
    create_resp = history_client.post("/api/v1/history/browse", json=browse_payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    item_id = created["id"]
    assert created["domain"] == "developer.mozilla.org"
    assert created["dwell_seconds"] == 45

    # 2. List browsing history
    list_resp = history_client.get("/api/v1/history/browse?session_id=test-session-history")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["id"] == item_id

    # 3. Export history bundle
    export_resp = history_client.get("/api/v1/history/export?session_id=test-session-history")
    assert export_resp.status_code == 200
    bundle = export_resp.json()
    assert bundle["total_visits"] == 1
    assert "exported_at" in bundle

    # 4. Delete single browse item
    del_resp = history_client.delete(f"/api/v1/history/browse/{item_id}")
    assert del_resp.status_code == 204

    # 5. Verify empty
    verify_resp = history_client.get("/api/v1/history/browse?session_id=test-session-history")
    assert verify_resp.json()["total"] == 0


def test_clear_search_history(history_client):
    # Search twice to populate history
    history_client.get("/api/v1/search?q=Quantum+algorithms")
    history_client.get("/api/v1/search?q=PostgreSQL+indexing")

    hist_resp = history_client.get("/api/v1/history/search")
    assert hist_resp.json()["total"] >= 2

    # Clear all search history
    clear_resp = history_client.delete("/api/v1/history/search")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["deleted_count"] >= 2

    # Verify cleared
    empty_resp = history_client.get("/api/v1/history/search")
    assert empty_resp.json()["total"] == 0
