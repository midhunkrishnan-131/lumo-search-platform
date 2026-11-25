"""Integration tests for AI Search API routes, RAG pipeline, and history recording."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.base import AIProviderResponse, BaseAIProvider
from app.ai.orchestrator import AISearchOrchestrator
from app.ai.router import AIProviderRouter
from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.models.history import SearchHistory
from app.semantic.indexer import semantic_indexer


class MockAIProvider(BaseAIProvider):
    def __init__(self, name: str = "mock-gemini") -> None:
        super().__init__(name=name)

    def is_configured(self) -> bool:
        return True

    def generate_grounded_answer(self, system_prompt: str, user_prompt: str, model=None, timeout=None) -> AIProviderResponse:
        return AIProviderResponse(
            content="Neural networks optimize representations [S1] through backpropagation.",
            provider=self.name,
            model="mock-v1",
            prompt_tokens=150,
            completion_tokens=20,
            total_tokens=170,
        )


@pytest.fixture
def ai_api_client(tmp_path, monkeypatch):
    db_file = tmp_path / "ai_api_test.db"
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

    # Disable remote vector timeout in tests
    semantic_indexer.store.base_url = "http://127.0.0.1:65530"
    semantic_indexer.store.timeout = 0.2

    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            id="doc-ai-rag-1",
            url="https://ml.example.org/neural-nets",
            domain="ml.example.org",
            title="Deep Neural Networks and Optimization",
            description="Foundations of backpropagation and deep learning representations.",
            main_content="Neural networks optimize representations through gradient-based backpropagation across layered parameters.",
            language="en",
            is_duplicate=False,
            content_hash="hash-ai-rag-1",
        )
        session.add(doc)
        session.commit()

        # Seed in semantic indexer
        semantic_indexer.index_document(doc.id, session)

    # Mock router to use MockAIProvider
    mock_router = AIProviderRouter(
        providers={"gemini": MockAIProvider("gemini"), "grok": MockAIProvider("grok")},
        primary_provider="gemini",
    )
    from app.ai import orchestrator as ai_orch_module
    monkeypatch.setattr(ai_orch_module, "ai_provider_router", mock_router)

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, session_factory

    dispose_database()


def test_ai_search_endpoint_success(ai_api_client):
    client, session_factory = ai_api_client
    payload = {
        "query": "How do neural networks optimize representations?",
        "page_size": 5,
    }
    resp = client.post("/api/v1/search/ai", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == payload["query"]
    assert data["status"] == "success"
    assert "Neural networks optimize representations" in data["answer"]
    assert "[S1]" in data["answer"]
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["citation_id"] == "[S1]"
    assert data["citations"][0]["url"] == "https://ml.example.org/neural-nets"
    assert len(data["sources"]) >= 1

    # Verify search history recorded with mode="ai"
    with session_factory() as session:
        entry = session.execute(
            select(SearchHistory).where(SearchHistory.query == payload["query"])
        ).scalars().first()
        assert entry is not None
        assert entry.mode == "ai"


def test_ai_search_question_alias(ai_api_client):
    """Verify frontend 'question' field alias is supported."""
    client, _ = ai_api_client
    payload = {
        "question": "How do neural networks optimize representations?",
        "max_sources": 4,
    }
    resp = client.post("/api/v1/search/ai", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["citations"]) >= 1


def test_ai_search_insufficient_evidence(ai_api_client):
    """When query finds no indexed documents, system returns insufficient_evidence without hallucinating."""
    client, _ = ai_api_client
    payload = {
        "query": "supercalifragilistic non-existent unindexed topic 9999",
    }
    resp = client.post("/api/v1/search/ai", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_evidence"
    assert "insufficient evidence" in data["answer"].lower()
    assert data["citations"] == []


def test_ai_search_privacy_mode(ai_api_client):
    """When privacy is True or X-History-Disabled header is sent, history is not recorded."""
    client, session_factory = ai_api_client
    payload = {
        "query": "Private secret AI research query",
        "privacy": True,
    }
    resp = client.post("/api/v1/search/ai", json=payload, headers={"X-History-Disabled": "true"})
    assert resp.status_code == 200

    with session_factory() as session:
        entry = session.execute(
            select(SearchHistory).where(SearchHistory.query == "Private secret AI research query")
        ).scalars().first()
        assert entry is None


def test_ai_status_endpoint(ai_api_client):
    client, _ = ai_api_client
    resp = client.get("/api/v1/search/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert "router" in data
    assert "providers" in data["router"]


def test_search_endpoint_with_mode_ai(ai_api_client):
    """Test GET /api/v1/search?q=...&mode=ai."""
    client, _ = ai_api_client
    resp = client.get("/api/v1/search?q=neural%20networks&mode=ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "neural networks"
    assert "ai_answer" in data["execution_metadata"]
