"""Integration tests for Guardian API endpoints."""

import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app


@pytest.fixture
def guardian_api_client(tmp_path):
    db_file = tmp_path / "guardian_api_test.db"
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
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, session_factory

    dispose_database()


def test_guardian_url_analysis_endpoint(guardian_api_client):
    client, _ = guardian_api_client

    # 1. Inspect public URL without network probe
    resp = client.post(
        "/api/v1/guardian/url",
        json={
            "url": "https://example.com/downloads/package.zip",
            "check_network": False,
            "check_reputation": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_type"] == "url"
    assert data["hostname"] == "example.com"
    assert "risk_level" in data
    assert "risk_score" in data
    assert "findings" in data
    analysis_id = data["id"]

    # 2. Fetch analysis report
    get_resp = client.get(f"/api/v1/guardian/analysis/{analysis_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == analysis_id

    # 3. Test SSRF blocked endpoint
    ssrf_resp = client.post(
        "/api/v1/guardian/url",
        json={"url": "http://127.0.0.1:8000/admin", "check_network": False},
    )
    assert ssrf_resp.status_code == 200
    ssrf_data = ssrf_resp.json()
    assert ssrf_data["risk_level"] == "Critical"
    assert ssrf_data["status"] == "blocked"


def test_guardian_file_analysis_endpoint(guardian_api_client):
    client, _ = guardian_api_client

    # Case A: Multipart file upload
    file_bytes = b"%PDF-1.7\n%LUMO Test PDF content\n<< /Type /Catalog >>\n"
    resp = client.post(
        "/api/v1/guardian/file",
        files={"file": ("report.pdf", io.BytesIO(file_bytes), "application/pdf")},
        data={"check_reputation": "false", "explain_ai": "false"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_type"] == "file"
    assert data["original_filename"] == "report.pdf"
    assert data["magic_signature"] == "PDF Document"
    assert len(data["sha256"]) == 64
    file_analysis_id = data["id"]

    # Case B: JSON Hash Lookup
    hash_resp = client.post(
        "/api/v1/guardian/file",
        json={
            "filename": "suspicious.exe",
            "size_bytes": 1024,
            "mime_type": "application/x-dosexec",
            "sha256": data["sha256"],
            "check_reputation": False,
        },
    )
    assert hash_resp.status_code == 200
    hash_data = hash_resp.json()
    assert hash_data["original_filename"] == "suspicious.exe"
    assert hash_data["sha256"] == data["sha256"]

    # Verify history listing
    hist_resp = client.get("/api/v1/guardian/history?limit=10&offset=0")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 2
    assert any(item["id"] == file_analysis_id for item in hist_data["items"])

    # Delete single analysis
    del_resp = client.delete(f"/api/v1/guardian/analysis/{file_analysis_id}")
    assert del_resp.status_code == 204

    # Clear history
    clear_resp = client.delete("/api/v1/guardian/history")
    assert clear_resp.status_code == 204

    hist_empty = client.get("/api/v1/guardian/history")
    assert hist_empty.json()["total"] == 0
