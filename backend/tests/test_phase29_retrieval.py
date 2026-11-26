"""Tests for LUMO Phase 29: Advanced Retrieval, Indexing, Chunking, Embeddings & Reranking."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import get_session_factory
from app.main import create_app
from app.models.document import Document
from app.retrieval.chunking import chunk_content
from app.retrieval.embeddings import CachedLocalEmbeddingProvider
from app.retrieval.engine import UnifiedRetrievalEngine
from app.retrieval.query_processor import process_query
from app.retrieval.reranker import rerank_candidates


@pytest.fixture()
def ret_client(tmp_path: Path):
    db_file = tmp_path / "phase29_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        log_level="WARNING",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        with get_session_factory()() as db:
            db.add(
                Document(
                    id="ret-doc-1",
                    url="https://example.com/rag",
                    title="Hybrid RAG Architecture",
                    main_content="Hybrid retrieval combines BM25 keyword search with vector similarity and RRF.",
                    content_hash="hretdoc1",
                    extraction_status="completed",
                    is_duplicate=False,
                )
            )
            db.commit()
        yield client


def test_chunking_embeddings_query_processing_and_reranker():
    # Format-aware chunking
    md_chunks = chunk_content("# Intro\nHello world.\n\n## Details\nFastAPI retrieval.", "d1", content_type="markdown", chunk_size=100, chunk_overlap=10)
    assert len(md_chunks) == 2
    assert md_chunks[0].section == "Intro"
    assert md_chunks[1].section == "Details"

    pdf_chunks = chunk_content("Page one text\fPage two text", "d2", content_type="pdf")
    assert len(pdf_chunks) == 2 and pdf_chunks[0].page_number == 1 and pdf_chunks[1].page_number == 2

    # Cached embedding provider
    emb = CachedLocalEmbeddingProvider(max_cache_size=32)
    v1 = emb.embed_batch(["hybrid search", "vector db"])
    v2 = emb.embed_batch(["hybrid search"])
    assert len(v1) == 2 and len(v1[0]) == emb.dimension
    assert v2[0] == v1[0]
    assert emb.stats()["cache_hits"] >= 1

    # Query processing preserves original & decomposes multi-part
    qp = process_query("What is FastAPI and how does RAG work?")
    assert qp["original_query"] == "What is FastAPI and how does RAG work?"
    assert qp["intent"] == "multi_part"
    assert len(qp["sub_queries"]) == 2

    # Reranker orders exact match higher and supports cancellation
    cands = [
        {"id": "1", "title": "Unrelated", "snippet": "cooking recipe", "score": 0.9},
        {"id": "2", "title": "Hybrid RAG", "snippet": "Hybrid RAG combines search", "score": 0.5},
    ]
    rr = rerank_candidates("Hybrid RAG", cands, top_k=2)
    assert rr[0]["id"] == "2"
    assert "Reranking" in rr[0]["explanations"]
    assert rerank_candidates("Hybrid RAG", cands, cancel_check=lambda: True) == []


def test_chunking_keeps_text_that_does_not_fit_the_open_chunk():
    """An oversized block after a short lead used to be sliced to chunk_size and the tail dropped."""
    tokens = [f"{i:03d}" for i in range(40)]
    long_para = "".join(tokens)
    text = f"Short lead.\n\n{long_para}\n\nClosing note."
    chunks = chunk_content(text, "d-long", content_type="text", chunk_size=40, chunk_overlap=10)
    blob = "\n".join(chunk.text for chunk in chunks)
    missing = [token for token in tokens if token not in blob]
    assert missing == []
    assert "Short lead." in blob
    assert "Closing note." in blob
    assert all(len(chunk.text) <= 40 for chunk in chunks)

    sentence = "Hello world. " + ("Z" * 100)
    sentence_chunks = chunk_content(sentence, "d-sent", content_type="text", chunk_size=30, chunk_overlap=5)
    sentence_blob = "\n".join(chunk.text for chunk in sentence_chunks)
    assert "Hello world." in sentence_blob
    assert sentence_blob.count("Z") >= 100
    assert all(len(chunk.text) <= 30 for chunk in sentence_chunks)

    markdown = "# Title\n\nShort.\n\n" + ("M" * 90)
    md_chunks = chunk_content(markdown, "d-md", content_type="markdown", chunk_size=40, chunk_overlap=8)
    md_blob = "\n".join(chunk.text for chunk in md_chunks)
    assert md_blob.count("M") >= 90
    assert any(chunk.section == "Title" for chunk in md_chunks)
    assert all(len(chunk.text) <= 40 for chunk in md_chunks)


def test_indexing_duplicate_detection_and_index_management(ret_client: TestClient):
    r1 = ret_client.post(
        "/api/v1/retrieval/index",
        json={"title": "Doc A", "content": "FastAPI uses Pydantic and SQLAlchemy for APIs.", "url": "https://example.com/a"},
    )
    assert r1.status_code == 201
    rec1 = r1.json()
    assert rec1["status"] == "indexed"
    assert rec1["chunk_count"] >= 1

    # Exact duplicate flagged safely without auto-deleting
    r2 = ret_client.post(
        "/api/v1/retrieval/index",
        json={"title": "Doc A Copy", "content": "FastAPI uses Pydantic and SQLAlchemy for APIs."},
    )
    assert r2.status_code == 201
    assert r2.json()["status"] == "duplicate_flagged"
    assert r2.json()["duplicate_of_id"] == rec1["id"]

    # Stats, reindex, confirmed delete
    stats = ret_client.get("/api/v1/retrieval/index/stats").json()
    assert stats["total_records"] == 2
    assert ret_client.post(f"/api/v1/retrieval/index/{rec1['id']}/reindex").status_code == 200
    assert ret_client.delete(f"/api/v1/retrieval/index/{rec1['id']}").status_code == 400  # requires confirm=true
    assert ret_client.delete(f"/api/v1/retrieval/index/{rec1['id']}?confirm=true").status_code == 200


def test_hybrid_retrieval_knowledge_hub_research_isolation_and_analytics(ret_client: TestClient):
    # Save owner-isolated Knowledge Hub item for Alice
    ret_client.post(
        "/api/v1/knowledge/items/save",
        headers={"X-LUMO-Owner": "alice"},
        json={"item_type": "SOURCE", "title": "Alice RAG Note", "content": "Hybrid retrieval notes for Alice."},
    )

    # Alice retrieves both document & Knowledge Hub item with explanations
    res_alice = ret_client.post(
        "/api/v1/retrieval/search",
        headers={"X-LUMO-Owner": "alice"},
        json={"query": "Hybrid retrieval", "mode": "classic", "include_knowledge_hub": True},
    ).json()
    assert res_alice["total"] >= 2
    assert any(r["source_type"].startswith("knowledge:") for r in res_alice["results"])
    assert all("explanations" in r for r in res_alice["results"])

    # Bob does NOT see Alice's Knowledge Hub item
    res_bob = ret_client.post(
        "/api/v1/retrieval/search",
        headers={"X-LUMO-Owner": "bob"},
        json={"query": "Alice RAG Note", "mode": "classic", "include_knowledge_hub": True},
    ).json()
    assert not any(r["title"] == "Alice RAG Note" for r in res_bob["results"])

    # Research contextual retrieval
    with get_session_factory()() as db:
        rr = UnifiedRetrievalEngine(db).retrieve_for_research("BM25 and vector similarity", owner_id="alice")
        assert len(rr["sub_queries"]) >= 1
        assert rr["total"] >= 1

    # Analytics endpoint
    an = ret_client.get("/api/v1/retrieval/analytics")
    assert an.status_code == 200
    assert "index_stats" in an.json()
