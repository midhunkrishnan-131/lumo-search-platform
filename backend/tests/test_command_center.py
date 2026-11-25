"""Deterministic tests for LUMO Phase 19: Intelligence Command Center (no paid API calls)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.automation import Automation, AutomationNotification
from app.models.document import Document
from app.models.graph import Entity
from app.models.guardian import GuardianAnalysis
from app.models.history import SearchHistory
from app.models.research import ResearchSession
from app.models.workspace import WorkspaceItem


@pytest.fixture()
def cc_client(tmp_path: Path):
    db_path = tmp_path / "cc_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_path}",
        gemini_api_key="AQ.SecretTestKey1234567890",
        grok_api_key="grok_SecretTestKey1234567890",
        local_only_ai=False,
    )
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


def _seed_platform_data():
    factory = get_session_factory()
    with factory() as db:
        db.add(
            Document(
                id="cc-doc-1",
                url="https://example.com/1",
                title="Web Doc",
                main_content="Indexed web content",
                content_hash="hcc1",
                is_duplicate=False,
            )
        )
        db.add(
            WorkspaceItem(
                id="cc-ws-1",
                title="Personal Note",
                content="Workspace knowledge",
                source_type="document",
                content_hash="hccws1",
            )
        )
        db.add(
            ResearchSession(
                id="cc-res-1",
                topic="Quantum Computing",
                status="completed",
                provider="gemini",
            )
        )
        db.add(
            Entity(
                id="cc-ent-1",
                name="FastAPI",
                normalized_name="fastapi",
                entity_type="Technology",
            )
        )
        db.add(
            Automation(
                id="cc-auto-1",
                name="Daily Digest",
                workflow_type="research",
                trigger_type="manual",
                enabled=True,
            )
        )
        db.add(
            AutomationNotification(
                id="cc-notif-1",
                automation_id="cc-auto-1",
                event_type="completed",
                title="Daily Digest Finished",
                message="Completed cleanly.",
                is_read=False,
            )
        )
        db.add(
            GuardianAnalysis(
                id="cc-guard-1",
                analysis_type="url",
                target="https://example.org/file.zip",
                risk_level="Low",
                risk_score=15,
                status="completed",
            )
        )
        db.add(
            SearchHistory(
                id="cc-search-1",
                query="LUMO Architecture",
                mode="hybrid",
                total_results=4,
            )
        )
        db.commit()


def test_command_center_aggregation_and_no_secret_exposure(cc_client: TestClient):
    _seed_platform_data()

    ov = cc_client.get("/api/v1/dashboard/overview")
    assert ov.status_code == 200
    m = ov.json()["metrics"]
    assert m["indexed_web_documents"] == 1
    assert m["personal_documents"] == 1
    assert m["research_reports"] == 1
    assert m["knowledge_graph_entities"] == 1
    assert m["active_automations"] == 1
    assert m["guardian_analyses"] == 1
    assert m["unread_notifications"] == 1

    # Activity feed + filtering + pagination
    act_all = cc_client.get("/api/v1/dashboard/activity?limit=2&offset=0").json()
    assert act_all["total"] >= 3
    assert len(act_all["items"]) == 2

    act_search = cc_client.get("/api/v1/dashboard/activity?category=search").json()
    assert act_search["total"] == 1
    assert act_search["items"][0]["category"] == "search"

    # Module overviews
    res = cc_client.get("/api/v1/dashboard/research").json()
    assert res["counts"]["completed"] == 1

    autos = cc_client.get("/api/v1/dashboard/automations").json()
    assert autos["counts"]["active"] == 1

    know = cc_client.get("/api/v1/dashboard/knowledge").json()
    assert know["graph"]["entities"] == 1

    guard = cc_client.get("/api/v1/dashboard/guardian").json()
    assert guard["total"] == 1
    assert "not definitive" in guard["disclaimer"].lower()

    notifs = cc_client.get("/api/v1/dashboard/notifications?unread_only=true").json()
    assert notifs["unread_count"] == 1

    # AI Status & System Health must never expose API keys
    ai_st = cc_client.get("/api/v1/dashboard/ai-status")
    assert ai_st.status_code == 200
    assert "SecretTestKey" not in ai_st.text

    health = cc_client.get("/api/v1/dashboard/system-health")
    assert health.status_code == 200
    assert "SecretTestKey" not in health.text
    assert health.json()["status"] == "healthy"


def test_command_center_partial_failure_resilience(cc_client: TestClient):
    _seed_platform_data()
    with patch("app.api.routes.dashboard._safe_count", side_effect=[0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        resp = cc_client.get("/api/v1/dashboard/overview")
        assert resp.status_code == 200
        assert resp.json()["metrics"]["personal_documents"] == 1
