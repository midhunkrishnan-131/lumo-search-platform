"""Tests for LUMO Phase 15: Offline AI Intelligence Engine (Local Ollama)."""

from collections.abc import Generator
import threading
import pytest
from fastapi.testclient import TestClient

from app.ai.base import AIProviderError, AIProviderResponse, BaseAIProvider
from app.ai.ollama import OllamaProvider
from app.ai.router import AIProviderRouter
from app.api.routes.local_ai import get_ollama_provider
from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


class MockOllamaProvider(OllamaProvider):
    """Mocked local Ollama provider for deterministic offline testing."""

    def __init__(self, reachable: bool = True, models: list[dict] | None = None):
        super().__init__(base_url="http://127.0.0.1:11434", default_model="llama3.2", enabled=True)
        self._reachable = reachable
        self._models = models if models is not None else [
            {
                "name": "llama3.2:latest",
                "size_bytes": 2_000_000_000,
                "size_gb": 1.86,
                "family": "llama",
                "parameter_size": "3B",
                "quantization": "Q4_K_M",
                "capabilities": ["chat", "summarization", "rag", "extraction"],
                "modified_at": "2026-11-25T10:00:00Z",
            }
        ]

    def check_health(self, timeout: float = 2.0):
        return {
            "reachable": self._reachable,
            "base_url": self.base_url,
            "models_count": len(self._models) if self._reachable else 0,
            "default_model": self.default_model,
        }

    def list_models(self, timeout: float = 3.0):
        return list(self._models)

    def chat(self, messages, model=None, timeout=None, temperature=0.2):
        return AIProviderResponse(
            content="Local summary grounded in workspace [L1] and ignoring [L99].",
            provider="ollama",
            model=model or self.default_model,
            prompt_tokens=20,
            completion_tokens=12,
            total_tokens=32,
        )

    def stream_chat(self, messages, model=None, timeout=None, cancel_event=None, temperature=0.2):
        for tok in ["Hello ", "from ", "local ", "Ollama!"]:
            if cancel_event is not None and cancel_event.is_set():
                yield {"token": "", "done": True, "cancelled": True, "model": model or self.default_model}
                return
            yield {"token": tok, "done": False, "cancelled": False, "model": model or self.default_model}
        yield {"token": "", "done": True, "cancelled": False, "model": model or self.default_model}


@pytest.fixture
def local_ai_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "local_ai.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        ollama_enabled=True,
        ollama_model="llama3.2",
        log_level="WARNING",
        cors_origins="http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    mock_prov = MockOllamaProvider()
    app = create_app(settings)
    app.dependency_overrides[get_ollama_provider] = lambda: mock_prov

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    dispose_database()


def test_local_ai_status_models_and_connection_test(local_ai_client: TestClient):
    status_resp = local_ai_client.get("/api/v1/local-ai/status")
    assert status_resp.status_code == 200
    st = status_resp.json()
    assert st["reachable"] is True
    assert st["models_count"] == 1

    models_resp = local_ai_client.get("/api/v1/local-ai/models")
    assert models_resp.status_code == 200
    assert models_resp.json()["models"][0]["name"] == "llama3.2:latest"

    test_resp = local_ai_client.post("/api/v1/local-ai/test", json={"model": "llama3.2:latest"})
    assert test_resp.status_code == 200
    assert test_resp.json()["success"] is True


def test_local_only_privacy_mode_blocks_external_providers():
    class DummyExternal(BaseAIProvider):
        def is_configured(self):
            return True

        def generate_grounded_answer(self, system_prompt, user_prompt, model=None, timeout=None):
            raise AssertionError("External provider MUST NOT be called in Local-Only Privacy Mode")

    mock_ollama = MockOllamaProvider()
    router = AIProviderRouter(
        providers={"gemini": DummyExternal("gemini"), "grok": DummyExternal("grok"), "ollama": mock_ollama},
        primary_provider="gemini",
        fallback_provider="grok",
        local_only_mode=True,
    )

    # Explicit external provider request is blocked
    with pytest.raises(AIProviderError, match="Local-Only Privacy Mode"):
        router.execute("sys", "user", requested_provider="gemini")

    with pytest.raises(AIProviderError, match="Local-Only Privacy Mode"):
        router.execute("sys", "user", requested_provider="grok")

    # Auto routes strictly to local Ollama even though primary_provider was gemini
    resp, fallback_used, active = router.execute("sys", "user", requested_provider="auto")
    assert active == "ollama"
    assert fallback_used is False
    assert resp.provider == "ollama"


def test_local_ai_chat_rag_grounding_and_streaming(local_ai_client: TestClient):
    # Seed a Personal Workspace item for RAG retrieval
    local_ai_client.post(
        "/api/v1/workspace/items",
        json={
            "title": "Offline RAG Notes",
            "content": "Offline RAG retrieves chunks from Qdrant and SQLite locally.",
            "source_type": "note",
        },
    )

    # Non-streaming RAG chat strips hallucinated [L99] and keeps [L1]
    chat_resp = local_ai_client.post(
        "/api/v1/local-ai/chat",
        json={
            "messages": [{"role": "user", "content": "How does Offline RAG work?"}],
            "use_rag": True,
            "rag_scope": "workspace",
        },
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert "[L1]" in data["answer"]
    assert "[L99]" not in data["answer"]
    assert len(data["citations"]) >= 1

    # SSE Streaming chat
    stream_resp = local_ai_client.post(
        "/api/v1/local-ai/chat/stream",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "use_rag": False,
        },
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")
    assert "Hello " in stream_resp.text
    assert "Ollama!" in stream_resp.text


def test_local_ai_task_engine_sync_and_cancel(local_ai_client: TestClient):
    # Sync summarization task
    task_resp = local_ai_client.post(
        "/api/v1/local-ai/tasks",
        json={
            "task_type": "summarize",
            "prompt": "Summarize local intelligence.",
            "use_rag": False,
            "run_async": False,
        },
    )
    assert task_resp.status_code == 200
    t_data = task_resp.json()
    assert t_data["status"] == "completed"
    assert t_data["task_type"] == "summarize"

    # Lookup task
    get_resp = local_ai_client.get(f"/api/v1/local-ai/tasks/{t_data['task_id']}")
    assert get_resp.status_code == 200

    # Cancel task
    cancel_resp = local_ai_client.post(f"/api/v1/local-ai/tasks/{t_data['task_id']}/cancel")
    assert cancel_resp.status_code == 200
