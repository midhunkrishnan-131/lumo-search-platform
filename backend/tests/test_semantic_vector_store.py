"""Unit tests for Qdrant REST client and persistent vector storage."""

import pytest
from app.semantic.vector_store import QdrantVectorStore


@pytest.fixture
def temp_vector_store(tmp_path):
    storage_path = tmp_path / "qdrant_test_storage"
    store = QdrantVectorStore(
        base_url="http://127.0.0.1:65530",  # Unreachable port to exercise persistent fallback
        collection_name="test_collection",
        storage_path=str(storage_path),
        dimension=4,
    )
    yield store


def test_upsert_and_cosine_search(temp_vector_store):
    # Normalized vectors
    points = [
        {
            "id": "point-1",
            "vector": [1.0, 0.0, 0.0, 0.0],
            "payload": {"document_id": "doc-a", "title": "Doc A", "domain": "a.com"},
        },
        {
            "id": "point-2",
            "vector": [0.0, 1.0, 0.0, 0.0],
            "payload": {"document_id": "doc-b", "title": "Doc B", "domain": "b.com"},
        },
    ]

    ok = temp_vector_store.upsert_points(points)
    assert ok is True
    assert temp_vector_store.count_vectors() == 2

    # Query vector identical to point-1
    matches = temp_vector_store.search_vectors([1.0, 0.0, 0.0, 0.0], limit=2)
    assert len(matches) == 2
    assert matches[0]["id"] == "point-1"
    assert abs(matches[0]["score"] - 1.0) < 1e-4


def test_search_with_domain_filter(temp_vector_store):
    points = [
        {
            "id": "point-1",
            "vector": [1.0, 0.0, 0.0, 0.0],
            "payload": {"document_id": "doc-a", "domain": "allowed.org"},
        },
        {
            "id": "point-2",
            "vector": [0.9, 0.1, 0.0, 0.0],
            "payload": {"document_id": "doc-b", "domain": "filtered.org"},
        },
    ]
    temp_vector_store.upsert_points(points)

    # Search with domain filter
    matches = temp_vector_store.search_vectors(
        [1.0, 0.0, 0.0, 0.0],
        limit=5,
        domain_filter="allowed.org",
    )
    assert len(matches) == 1
    assert matches[0]["id"] == "point-1"


def test_delete_by_document_id(temp_vector_store):
    points = [
        {
            "id": "point-1",
            "vector": [1.0, 0.0, 0.0, 0.0],
            "payload": {"document_id": "doc-to-del"},
        },
        {
            "id": "point-2",
            "vector": [0.0, 1.0, 0.0, 0.0],
            "payload": {"document_id": "doc-to-keep"},
        },
    ]
    temp_vector_store.upsert_points(points)
    assert temp_vector_store.count_vectors() == 2

    temp_vector_store.delete_document_vectors("doc-to-del")
    assert temp_vector_store.count_vectors() == 1
