"""FastAPI route tests for LUMO Phase 11 Knowledge Graph endpoints."""

from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.models.graph import Entity, Relationship, RelationshipEvidence


@pytest.fixture
def app_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "test_graph.db"
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

    # Seed sample entities and relationships
    factory = get_session_factory()
    with factory() as db:
        e1 = Entity(
            id="e-fastapi",
            name="FastAPI",
            normalized_name="fastapi",
            entity_type="Technology",
            description="High-performance Python web framework.",
            confidence=1.0,
            extraction_method="rule_based",
        )
        e2 = Entity(
            id="e-python",
            name="Python",
            normalized_name="python",
            entity_type="Technology",
            description="Interpreted programming language.",
            confidence=1.0,
            extraction_method="rule_based",
        )
        r1 = Relationship(
            id="r-uses",
            source_id="e-fastapi",
            target_id="e-python",
            relationship_type="USES",
            confidence=0.9,
            extraction_method="syntactic_pattern",
            weight=1.0,
        )
        db.add_all([e1, e2, r1])
        db.commit()

    with TestClient(create_app(settings)) as client:
        yield client

    dispose_database()


def test_get_graph_overview(app_client: TestClient):
    response = app_client.get("/api/v1/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert data["total_nodes"] == 2
    assert data["total_edges"] == 1
    assert any(n["label"] == "FastAPI" for n in data["nodes"])


def test_get_graph_overview_filtering(app_client: TestClient):
    # Filter by matching type
    resp_match = app_client.get("/api/v1/graph?type=Technology")
    assert resp_match.status_code == 200
    assert len(resp_match.json()["nodes"]) == 2

    # Filter by non-matching type
    resp_empty = app_client.get("/api/v1/graph?type=Location")
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()["nodes"]) == 0

    # Search filter
    resp_search = app_client.get("/api/v1/graph?q=Python")
    assert resp_search.status_code == 200
    assert len(resp_search.json()["nodes"]) == 1


def test_get_graph_stats(app_client: TestClient):
    response = app_client.get("/api/v1/graph/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entities"] == 2
    assert data["total_relationships"] == 1
    assert data["entities_by_type"].get("Technology") == 2
    assert data["relationships_by_type"].get("USES") == 1


def test_search_graph_entities(app_client: TestClient):
    response = app_client.get("/api/v1/graph/search?q=FastAPI")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "FastAPI"


def test_get_entity_detail_success_and_404(app_client: TestClient):
    # Success
    resp_ok = app_client.get("/api/v1/graph/entities/e-fastapi")
    assert resp_ok.status_code == 200
    detail = resp_ok.json()
    assert detail["name"] == "FastAPI"
    assert detail["entity_type"] == "Technology"
    assert len(detail["relationships"]) == 1

    # 404
    resp_404 = app_client.get("/api/v1/graph/entities/non-existent-entity")
    assert resp_404.status_code == 404


def test_get_entity_connections(app_client: TestClient):
    resp = app_client.get("/api/v1/graph/entities/e-fastapi/connections?depth=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["depth"] == 1
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_reprocess_endpoint(app_client: TestClient):
    resp = app_client.post("/api/v1/graph/reprocess", json={"batch_size": 10, "use_ai": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
