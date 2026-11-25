"""Phase 12 End-to-End Platform Integration, Diagnostics, CORS, and Security Tests."""

from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.graph.service import invalidate_graph_cache
from app.main import create_app


@pytest.fixture
def integration_client(tmp_path) -> Generator[TestClient, None, None]:
    invalidate_graph_cache()
    db_file = tmp_path / "integration_lumo.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        gemini_api_key="super-secret-gemini-key-should-never-leak",
        guardian_virustotal_api_key="super-secret-vt-key",
        log_level="WARNING",
        cors_origins="http://localhost:3000,http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    with TestClient(create_app(settings)) as client:
        yield client

    invalidate_graph_cache()
    dispose_database()


def test_diagnostics_endpoint_exposes_status_without_secrets(integration_client: TestClient):
    resp = integration_client.get("/api/v1/health/diagnostics")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "healthy"
    assert data["application"] == "LUMO"
    assert data["database"]["status"] == "connected"
    assert data["database"]["dialect"] == "sqlite"
    assert data["ai_providers"]["gemini_configured"] is True
    assert data["guardian"]["virustotal_configured"] is True

    # Ensure zero secret leakage in JSON payload
    raw_text = resp.text
    assert "super-secret-gemini-key" not in raw_text
    assert "super-secret-vt-key" not in raw_text
    assert "integration_lumo.db" not in raw_text


def test_cors_allows_delete_preflight(integration_client: TestClient):
    resp = integration_client.options(
        "/api/v1/documents/doc-123",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert resp.status_code == 200
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "DELETE" in allow_methods


def test_end_to_end_document_lifecycle_search_and_graph_sync(integration_client: TestClient):
    html_payload = """
    <html>
      <head><title>FastAPI and Python Integration</title></head>
      <body>
        <main>
          <h1>FastAPI Architecture</h1>
          <p>FastAPI uses Python and integrates with Qdrant for semantic vector search.</p>
        </main>
      </body>
    </html>
    """
    # 1. Process HTML document
    proc_resp = integration_client.post(
        "/api/v1/documents/process",
        json={"url": "https://example.org/fastapi-guide", "html": html_payload},
    )
    assert proc_resp.status_code == 201
    doc_data = proc_resp.json()
    doc_id = doc_data["id"]

    # 2. Verify Classic Search finds the document
    search_resp = integration_client.get("/api/v1/search?q=FastAPI&mode=classic")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] >= 1
    assert any(item["url"] == "https://example.org/fastapi-guide" for item in search_data["results"])

    # 3. Verify Knowledge Graph automatically indexed entities & relationships
    graph_resp = integration_client.get("/api/v1/graph")
    assert graph_resp.status_code == 200
    graph_data = graph_resp.json()
    node_labels = {n["label"] for n in graph_data["nodes"]}
    assert "FastAPI" in node_labels
    assert "Python" in node_labels

    # 4. Delete Document and verify synchronized Knowledge Graph cleanup
    del_resp = integration_client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 204

    # Graph should now be empty (orphaned entities cleaned up)
    graph_after = integration_client.get("/api/v1/graph").json()
    assert graph_after["total_nodes"] == 0
    assert graph_after["total_edges"] == 0


def test_guardian_ssrf_protection_in_integration(integration_client: TestClient):
    resp = integration_client.post(
        "/api/v1/guardian/url",
        json={"url": "http://169.254.169.254/latest/meta-data/", "check_network": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["risk_level"] == "Critical"
