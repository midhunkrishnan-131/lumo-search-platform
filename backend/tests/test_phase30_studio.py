"""Tests for LUMO Phase 30: Intelligence Studio & Deliverable Engine."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.ai.base import AIProviderResponse, BaseAIProvider
from app.ai.router import AIProviderRouter
from app.config import Settings
from app.database.connection import get_session_factory
from app.main import create_app
from app.schemas.studio import StudioAIAssistRequest
from app.studio.service import StudioService


@pytest.fixture()
def studio_client(tmp_path: Path):
    db_file = tmp_path / "phase30_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        log_level="WARNING",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client


def test_studio_project_templates_versions_import_citations_and_export(studio_client: TestClient):
    # 1. Templates
    tpls = studio_client.get("/api/v1/studio/templates")
    assert tpls.status_code == 200
    assert len(tpls.json()) == 6

    # 2. Create project
    p = studio_client.post(
        "/api/v1/studio/projects",
        json={"title": "LUMO Q4 Report", "document_type": "research_report"},
    ).json()
    assert p["version_number"] == 1
    assert len(p["sections"]) >= 5

    # 3. Import Knowledge Hub item & CSV data analysis chart
    kh = studio_client.post(
        "/api/v1/knowledge/items/save",
        json={"item_type": "SOURCE", "title": "Benchmark Note", "url": "https://example.com/bm", "content": "Hybrid RRF improves recall."},
    ).json()
    p_imp1 = studio_client.post(
        f"/api/v1/studio/projects/{p['id']}/import",
        json={"source_type": "knowledge_item", "source_id": kh["id"]},
    ).json()
    assert len(p_imp1["sources"]) == 1
    assert p_imp1["sources"][0]["citation_id"] == "S1"

    p_imp2 = studio_client.post(
        f"/api/v1/studio/projects/{p['id']}/import",
        json={"source_type": "data_analysis", "title": "Metrics CSV", "csv_content": "mode,score\nclassic,0.7\nhybrid,0.9\n"},
    ).json()
    assert len(p_imp2["charts"]) == 1

    # 4. Citation validation
    cit = studio_client.get(f"/api/v1/studio/projects/{p['id']}/citations/validate").json()
    assert "S1" in cit["valid_citations"]
    assert cit["invalid_citations"] == []

    # 5. Update + non-destructive version restore
    studio_client.put(
        f"/api/v1/studio/projects/{p['id']}",
        json={"executive_summary": "Updated summary [S1]", "change_summary": "Added summary"},
    )
    vers = studio_client.get(f"/api/v1/studio/projects/{p['id']}/versions").json()
    assert len(vers) >= 4
    v1 = [v for v in vers if v["version_number"] == 1][0]
    restored = studio_client.post(f"/api/v1/studio/projects/{p['id']}/versions/{v1['id']}/restore").json()
    assert restored["version_number"] > 4
    assert restored["executive_summary"] == ""

    # 6. Presentation outline, Preview, Exports & Save to Knowledge Hub
    slides = studio_client.post(f"/api/v1/studio/projects/{p['id']}/presentation-outline").json()
    assert slides["slide_count"] >= 2
    assert studio_client.get(f"/api/v1/studio/projects/{p['id']}/preview").status_code == 200
    assert "# LUMO Q4 Report" in studio_client.get(f"/api/v1/studio/projects/{p['id']}/export?format=markdown").text
    assert studio_client.get(f"/api/v1/studio/projects/{p['id']}/export?format=json").json()["id"] == p["id"]
    kh_saved = studio_client.post(f"/api/v1/studio/projects/{p['id']}/save-to-knowledge", json={})
    assert kh_saved.status_code == 200


class _MockStudioProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__(name="gemini")

    def is_configured(self) -> bool:
        return True

    def generate_grounded_answer(self, system_prompt: str, user_prompt: str, model: str | None = None, timeout: float | None = None) -> AIProviderResponse:
        return AIProviderResponse(content="Drafted executive summary preview.", model="mock", provider="gemini")


def test_studio_ai_assist_isolation_and_permissions(studio_client: TestClient):
    # Owner isolation
    alice_p = studio_client.post(
        "/api/v1/studio/projects",
        headers={"X-LUMO-Owner": "alice"},
        json={"title": "Alice Deliverable", "document_type": "briefing"},
    ).json()
    assert studio_client.get(f"/api/v1/studio/projects/{alice_p['id']}", headers={"X-LUMO-Owner": "bob"}).status_code == 404

    # Mocked AI assist returns preview without overwriting executive_summary
    with get_session_factory()() as db:
        router = AIProviderRouter(providers={"gemini": _MockStudioProvider()}, primary_provider="gemini", local_only_mode=False)
        svc = StudioService(db, ai_router=router)
        res = svc.ai_assist(alice_p["id"], StudioAIAssistRequest(action="generate_executive_summary", input_text="Notes"), owner_id="alice")
        assert res["status"] == "preview_ready"
        assert res["preview_text"] == "Drafted executive summary preview."
        assert svc.get_project(alice_p["id"], owner_id="alice")["executive_summary"] == ""

    # Duplicate & Permissions
    assert studio_client.post(f"/api/v1/studio/projects/{alice_p['id']}/duplicate", headers={"X-LUMO-Owner": "alice"}).status_code == 201
    ro_key = studio_client.post("/api/v1/developer/keys", json={"name": "StudioRO", "permissions": ["documents:read"]}).json()["raw_key"]
    assert studio_client.get("/api/v1/studio/projects", headers={"X-API-Key": ro_key}).status_code == 200
    assert studio_client.post("/api/v1/studio/projects", headers={"X-API-Key": ro_key}, json={"title": "Blocked"}).status_code == 403
