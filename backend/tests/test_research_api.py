"""Integration tests for Research API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.research import ResearchSession


@pytest.fixture
def research_api_client(tmp_path):
    db_file = tmp_path / "research_api_test.db"
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


def test_research_session_lifecycle(research_api_client):
    client, session_factory = research_api_client

    # 1. Create a session with auto_start=False
    resp = client.post(
        "/api/v1/research",
        json={
            "query": "Impact of Dense Vectors on Retrieval Accuracy",
            "max_iterations": 2,
            "max_queries": 6,
            "max_sources": 10,
            "auto_start": False,
        },
    )
    assert resp.status_code == 201
    created_data = resp.json()
    session_id = created_data["id"]
    assert created_data["status"] == "pending"
    assert created_data["topic"] == "Impact of Dense Vectors on Retrieval Accuracy"
    assert created_data["max_iterations"] == 2

    # 2. Get session detail
    detail_resp = client.get(f"/api/v1/research/{session_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == session_id

    # 3. Cancel session
    cancel_resp = client.post(f"/api/v1/research/{session_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # 4. List sessions
    list_resp = client.get("/api/v1/research?limit=10&offset=0")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(s["id"] == session_id for s in list_data["items"])

    # 5. Delete session
    del_resp = client.delete(f"/api/v1/research/{session_id}")
    assert del_resp.status_code == 204

    # 6. Verify deleted (404)
    get_del = client.get(f"/api/v1/research/{session_id}")
    assert get_del.status_code == 404


def test_research_report_and_sources_endpoints(research_api_client):
    client, session_factory = research_api_client

    with session_factory() as session:
        mock_session = ResearchSession(
            id="session-report-test",
            topic="Benchmarking BM25 vs Vectors",
            status="completed",
            report_markdown="# Benchmarking Report\n\nHybrid is superior [S1].",
            sources=[
                {
                    "source_id": "S1",
                    "title": "Benchmark Paper",
                    "url": "https://arxiv.org/abs/test",
                    "domain": "arxiv.org",
                    "passage": "Hybrid search scores highest.",
                }
            ],
            findings=[
                {
                    "kind": "Supported Finding",
                    "text": "Hybrid search beats pure vector retrieval [S1].",
                    "citations": ["S1"],
                }
            ],
        )
        session.add(mock_session)
        session.commit()

    # Get Report
    report_resp = client.get("/api/v1/research/session-report-test/report")
    assert report_resp.status_code == 200
    rep_data = report_resp.json()
    assert rep_data["status"] == "completed"
    assert "Hybrid is superior [S1]" in rep_data["report_markdown"]
    assert len(rep_data["sources"]) == 1

    # Get Sources
    sources_resp = client.get("/api/v1/research/session-report-test/sources")
    assert sources_resp.status_code == 200
    assert len(sources_resp.json()) == 1
    assert sources_resp.json()[0]["source_id"] == "S1"


def test_research_create_validation_error(research_api_client):
    client, _ = research_api_client

    # Empty query should return 422
    resp = client.post("/api/v1/research", json={"query": ""})
    assert resp.status_code == 422
