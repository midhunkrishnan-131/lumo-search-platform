"""Tests for LUMO Phase 28: Personal Knowledge Hub & Persistent Intelligence."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def kh_client(tmp_path: Path):
    db_file = tmp_path / "phase28_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        log_level="WARNING",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client


def test_collections_save_dedup_move_and_non_destructive_delete(kh_client: TestClient):
    col1 = kh_client.post("/api/v1/knowledge/collections", json={"name": "AI Research", "tags": ["ai"]}).json()
    col2 = kh_client.post("/api/v1/knowledge/collections", json={"name": "Python Dev"}).json()

    # Save item into col1 with note and tags
    saved = kh_client.post(
        "/api/v1/knowledge/items/save",
        json={
            "item_type": "RESEARCH_REPORT",
            "title": "FastAPI Evaluation Summary",
            "description": "Findings on FastAPI",
            "content": "FastAPI supports async Python endpoints and Pydantic validation.",
            "collection_id": col1["id"],
            "tags": ["Python", "FastAPI"],
            "note": "Initial review note",
        },
    )
    assert saved.status_code == 201
    item = saved.json()
    assert item["deduplicated"] is False

    # Duplicate save returns deduplicated=True
    dup = kh_client.post(
        "/api/v1/knowledge/items/save",
        json={
            "item_type": "RESEARCH_REPORT",
            "title": "FastAPI Evaluation Summary",
            "description": "Findings on FastAPI",
            "content": "FastAPI supports async Python endpoints and Pydantic validation.",
        },
    ).json()
    assert dup["deduplicated"] is True
    assert dup["id"] == item["id"]

    # Move item to col2
    moved = kh_client.patch(f"/api/v1/knowledge/items/{item['id']}/move", json={"collection_id": col2["id"]})
    assert moved.status_code == 200
    assert moved.json()["collection_id"] == col2["id"]

    # Deleting col2 does NOT delete the underlying saved item
    assert kh_client.delete(f"/api/v1/knowledge/collections/{col2['id']}").status_code == 200
    still_there = kh_client.get(f"/api/v1/knowledge/items/{item['id']}")
    assert still_there.status_code == 200
    assert still_there.json()["collection_id"] is None


def test_search_notes_tags_relationships_recommendations_and_timeline(kh_client: TestClient):
    i1 = kh_client.post(
        "/api/v1/knowledge/items/save",
        json={"item_type": "SOURCE", "title": "Qdrant Docs", "content": "Vector database for semantic search", "tags": ["vector"]},
    ).json()
    i2 = kh_client.post(
        "/api/v1/knowledge/items/save",
        json={"item_type": "DOCUMENT", "title": "Hybrid Search Design", "content": "Combines BM25 and vector search", "tags": ["vector"]},
    ).json()

    # Search by keyword & tag
    sr = kh_client.post("/api/v1/knowledge/search", json={"query": "vector", "tag": "vector"})
    assert sr.status_code == 200
    assert len(sr.json()) == 2

    # Tag rename
    ren = kh_client.put("/api/v1/knowledge/tags/vector", json={"new_name": "VectorDB"})
    assert ren.status_code == 200
    assert ren.json()["name"] == "vectordb"

    # Notes CRUD
    note = kh_client.post("/api/v1/knowledge/notes", json={"title": "Design Note", "content": "Check RRF weights"}).json()
    assert kh_client.put(f"/api/v1/knowledge/notes/{note['id']}", json={"content": "Updated RRF weights"}).status_code == 200
    assert len(kh_client.get("/api/v1/knowledge/notes?q=Updated").json()) == 1

    # Explicit relationship & recommendations (verified vs inferred)
    rel = kh_client.post(
        "/api/v1/knowledge/relationships",
        json={"source_item_id": i2["id"], "target_item_id": i1["id"], "relationship_type": "REFERENCES", "evidence": "Uses Qdrant"},
    )
    assert rel.status_code == 201
    recs = kh_client.get(f"/api/v1/knowledge/items/{i1['id']}/recommendations").json()
    assert len(recs["verified_relationships"]) == 1
    assert len(recs["suggested_connections"]) >= 1
    assert recs["suggested_connections"][0]["is_inferred"] is True

    # Timeline
    tl = kh_client.get("/api/v1/knowledge/timeline")
    assert tl.status_code == 200
    assert len(tl.json()) >= 4


def test_context_workflow_integration_import_export_isolation_and_permissions(kh_client: TestClient):
    # Owner isolation
    alice_item = kh_client.post(
        "/api/v1/knowledge/items/save",
        headers={"X-LUMO-Owner": "alice"},
        json={"item_type": "AI_ANSWER", "title": "Alice Secret", "content": "Alice private research on FastAPI."},
    ).json()
    assert kh_client.get(f"/api/v1/knowledge/items/{alice_item['id']}", headers={"X-LUMO-Owner": "bob"}).status_code == 404

    # Context retrieval + workflow integration
    ctx = kh_client.post(
        "/api/v1/knowledge/context",
        headers={"X-LUMO-Owner": "alice"},
        json={"item_ids": [alice_item["id"]]},
    ).json()
    assert "[K1]" in ctx["context_text"]

    wf = kh_client.post(
        "/api/v1/workflows",
        headers={"X-LUMO-Owner": "alice"},
        json={"user_request": "Extract entities", "preferred_intent": "KNOWLEDGE_GRAPH", "inputs": {"knowledge_item_ids": [alice_item["id"]]}},
    ).json()
    wf_done = kh_client.post(f"/api/v1/workflows/{wf['id']}/execute", headers={"X-LUMO-Owner": "alice"}, json={}).json()
    assert wf_done["status"] == "COMPLETED"

    # Export & Import with deduplication
    exp_json = kh_client.get("/api/v1/knowledge/export?format=json", headers={"X-LUMO-Owner": "alice"}).json()
    assert len(exp_json["items"]) == 1
    imp = kh_client.post("/api/v1/knowledge/import", headers={"X-LUMO-Owner": "alice"}, json=exp_json).json()
    assert imp["duplicates_skipped"] == 1

    # API Key permission enforcement (workspace:read vs workspace:write)
    ro_key = kh_client.post("/api/v1/developer/keys", json={"name": "KHRead", "permissions": ["workspace:read"]}).json()["raw_key"]
    assert kh_client.get("/api/v1/knowledge/dashboard", headers={"X-API-Key": ro_key}).status_code == 200
    assert kh_client.post("/api/v1/knowledge/collections", headers={"X-API-Key": ro_key}, json={"name": "Blocked"}).status_code == 403
