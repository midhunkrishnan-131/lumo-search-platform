"""Tests for LUMO Web Platform Optimization & Production Engineering."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


def test_security_headers_and_expanded_diagnostics(tmp_path):
    db_file = tmp_path / "prod_check.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="development",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    try:
        with TestClient(create_app(settings)) as client:
            resp = client.get("/api/v1/health/diagnostics")
            assert resp.status_code == 200
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
            assert resp.headers.get("X-Frame-Options") == "DENY"
            assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
            assert "Permissions-Policy" in resp.headers

            data = resp.json()
            assert "workspace" in data
            assert "crawler" in data
            assert "knowledge_graph" in data
            assert data["workspace"]["total_items"] == 0
            assert data["crawler"]["total_sessions"] == 0
    finally:
        dispose_database()


def test_production_mode_disables_openapi_and_docs(tmp_path):
    db_file = tmp_path / "prod_only.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="production",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="https://search.example.com",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    try:
        with TestClient(create_app(settings)) as client:
            assert client.get("/docs").status_code == 404
            assert client.get("/openapi.json").status_code == 404
            assert client.get("/api/v1/health").status_code == 200
    finally:
        dispose_database()
