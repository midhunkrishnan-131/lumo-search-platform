"""Tests for LUMO Live Public Internet Search, SSRF-Safe Extraction, and AI Search Integration."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.ai.base import AIProviderResponse, BaseAIProvider
from app.ai.orchestrator import AISearchOrchestrator
from app.ai.router import AIProviderRouter
from app.config import Settings
from app.database.connection import get_session_factory
from app.main import create_app
from app.schemas.ai import AISearchRequest
from app.search.web_provider import PublicMultiWebSearchProvider


@pytest.fixture()
def web_client(tmp_path: Path):
    db_file = tmp_path / "web_search_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        log_level="WARNING",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client


def test_ssrf_blocked_in_extract_endpoint(web_client: TestClient):
    for bad_url in (
        "http://127.0.0.1:8000/health",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
    ):
        resp = web_client.post("/api/v1/search/extract", json={"url": bad_url})
        assert resp.status_code == 400


def test_live_web_search_queries_and_site_filter(web_client: TestClient):
    for q in (
        "Latest Python release",
        "Current technology news",
        "What is artificial intelligence?",
        "site:en.wikipedia.org Python",
    ):
        resp = web_client.get("/api/v1/search/web", params={"q": q, "per_page": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "web"
        assert body["total"] >= 1
        assert all(r["url"].startswith("http") and "lumo.local" not in r["url"] and r["title"] for r in body["results"])


def test_web_provider_failure_surfaces_502_and_modes_isolated(web_client: TestClient, monkeypatch):
    # Classic/Hybrid on empty DB returns 0 local results without hitting live web
    c_resp = web_client.get("/api/v1/search", params={"q": "Latest Python release", "mode": "classic"})
    assert c_resp.status_code == 200
    assert c_resp.json()["total"] == 0

    # Provider failure on /search/web returns 502 instead of silently falling back to local index
    from app.api.routes import search as search_route

    def _boom(*args, **kwargs):
        raise RuntimeError("Live web search providers failed: upstream timeout")

    monkeypatch.setattr(search_route.live_web_provider, "search", _boom)
    fail_resp = web_client.get("/api/v1/search/web", params={"q": "python"})
    assert fail_resp.status_code == 502
    assert "Live web search providers failed" in fail_resp.json()["detail"]


class _GroundedMockProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__(name="gemini")

    def is_configured(self) -> bool:
        return True

    def generate_grounded_answer(self, system_prompt: str, user_prompt: str, model: str | None = None, timeout: float | None = None) -> AIProviderResponse:
        # Cite [S1] and include a hallucinated [S99] to verify CitationValidator strips [S99]
        return AIProviderResponse(
            content="Artificial intelligence is computer intelligence [S1]. Unsupported claim [S99].",
            model="mock",
            provider="gemini",
        )


def test_ai_search_uses_live_web_and_validates_citations(web_client: TestClient):
    with get_session_factory()() as db:
        router = AIProviderRouter(providers={"gemini": _GroundedMockProvider()}, primary_provider="gemini", local_only_mode=False)
        orch = AISearchOrchestrator(db=db, router=router)
        res = orch.search(AISearchRequest(query="what is artificial intelligence", page_size=5))
        assert res.status == "success"
        assert len(res.sources) >= 1
        assert len(res.citations) >= 1
        assert "[S1]" in res.answer
        assert "[S99]" not in res.answer
