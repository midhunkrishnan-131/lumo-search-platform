"""Tests for LUMO Phase 16: Intelligence Automation Engine."""

from collections.abc import Generator
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient

from app.automation.conditions import evaluate_condition
from app.automation.engine import automation_manager, utc_now
from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.automation import Automation, AutomationExecution
from app.models.document import Document


@pytest.fixture
def auto_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "automation_test.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    with TestClient(create_app(settings)) as client:
        yield client

    dispose_database()


def test_templates_crud_pause_resume_duplicate(auto_client: TestClient):
    tpls = auto_client.get("/api/v1/automations/templates").json()
    assert len(tpls) == 6
    assert any(t["id"] == "research_monitor" for t in tpls)

    # Create
    create_resp = auto_client.post(
        "/api/v1/automations",
        json={
            "name": "My Monitor",
            "description": "Tracks FastAPI",
            "workflow_type": "research_monitor",
            "trigger_type": "scheduled",
            "trigger_config": {"interval": "daily", "topic": "FastAPI"},
            "steps": [{"id": "s1", "type": "search", "config": {"query": "FastAPI"}}],
        },
    )
    assert create_resp.status_code == 201
    auto_id = create_resp.json()["id"]
    assert create_resp.json()["next_run_at"] is not None

    # Pause & Resume
    assert auto_client.post(f"/api/v1/automations/{auto_id}/pause").json()["enabled"] is False
    assert auto_client.post(f"/api/v1/automations/{auto_id}/resume").json()["enabled"] is True

    # Duplicate
    dup = auto_client.post(f"/api/v1/automations/{auto_id}/duplicate")
    assert dup.status_code == 201
    assert "(Copy)" in dup.json()["name"]
    assert dup.json()["enabled"] is False

    # Delete
    assert auto_client.delete(f"/api/v1/automations/{auto_id}").status_code == 204


def test_research_monitor_execution_change_detection_and_notifications(auto_client: TestClient):
    # Seed indexed document
    factory = get_session_factory()
    with factory() as db:
        db.add(
            Document(
                id="doc-auto-1",
                url="https://example.org/fastapi-news",
                title="FastAPI Release Notes",
                main_content="FastAPI uses Python and Pydantic for fast APIs.",
                content_hash="hash-auto-1",
                extraction_status="completed",
                is_duplicate=False,
            )
        )
        db.commit()

    # Create Research Monitor automation
    auto = auto_client.post(
        "/api/v1/automations",
        json={
            "name": "FastAPI Monitor",
            "workflow_type": "research_monitor",
            "trigger_type": "manual",
            "trigger_config": {"topic": "FastAPI"},
            "steps": [
                {"id": "s1", "type": "search", "config": {"query": "FastAPI"}},
                {"id": "s2", "type": "condition", "config": {"condition_type": "new_info_detected"}},
                {"id": "s3", "type": "report_generate", "config": {"title_prefix": "Monitor Report"}},
                {"id": "s4", "type": "workspace_save", "config": {"source_type": "research_report"}},
                {"id": "s5", "type": "notification", "config": {"event_type": "new_info_detected"}},
            ],
        },
    ).json()

    # First run: detects 1 new source -> saves to Workspace & creates notification
    run1 = auto_client.post(f"/api/v1/automations/{auto['id']}/run?sync=true").json()
    assert run1["status"] == "completed"
    assert run1["workspace_item_id"] is not None
    assert len(run1["step_logs"]) == 5

    # Second run with no new documents: condition new_info_detected halts cleanly at step 2
    run2 = auto_client.post(f"/api/v1/automations/{auto['id']}/run?sync=true").json()
    assert run2["status"] == "completed"
    assert run2["workspace_item_id"] is None
    assert len(run2["step_logs"]) == 2

    # Notifications check
    notifs = auto_client.get("/api/v1/notifications").json()
    assert len(notifs) >= 1
    nid = notifs[0]["id"]
    assert auto_client.post(f"/api/v1/notifications/{nid}/read").json()["is_read"] is True
    assert auto_client.delete(f"/api/v1/notifications/{nid}").status_code == 204


def test_event_trigger_scheduled_trigger_limits_and_recovery(auto_client: TestClient):
    # Create event-triggered Document Intelligence automation
    ev_auto = auto_client.post(
        "/api/v1/automations",
        json={
            "name": "Doc Intel",
            "workflow_type": "document_intelligence",
            "trigger_type": "event",
            "trigger_config": {"event_name": "document_indexed"},
            "max_executions_per_day": 1,
            "steps": [
                {"id": "s1", "type": "document_analysis", "config": {}},
                {"id": "s2", "type": "tag_assign", "config": {"tags": ["indexed"]}},
            ],
        },
    ).json()

    factory = get_session_factory()
    with factory() as db:
        exec_ids = automation_manager.emit_event(
            db,
            "document_indexed",
            payload={"title": "Python Doc", "text": "FastAPI uses Python and Qdrant."},
            run_sync=True,
        )
        assert len(exec_ids) == 1

        # Daily quota (max_executions_per_day=1) blocks second run
        with pytest.raises(ValueError, match="Daily execution limit"):
            automation_manager.trigger_automation(db, ev_auto["id"], trigger_source="manual", run_sync=True)

        # Simulate interrupted execution recovery on startup
        stale = AutomationExecution(
            id="exec-stale-1",
            automation_id=ev_auto["id"],
            status="running",
            total_steps=2,
        )
        db.add(stale)
        db.commit()

        recovered = automation_manager.recover_interrupted_executions(db)
        assert recovered == 1
        db.refresh(stale)
        assert stale.status == "failed"
        assert "restart" in stale.error_message.lower()


def test_condition_evaluator_and_security_validation(auto_client: TestClient):
    ctx = {"sources": [{"title": "Python Guide", "snippet": "Async FastAPI"}], "new_sources_count": 1}
    assert evaluate_condition({"condition_type": "results_exist"}, ctx)[0] is True
    assert evaluate_condition({"condition_type": "min_count", "threshold": 2}, ctx)[0] is False
    assert evaluate_condition({"condition_type": "keyword_present", "keyword": "fastapi"}, ctx)[0] is True

    # Invalid step type rejected by Pydantic validation (422)
    bad_resp = auto_client.post(
        "/api/v1/automations",
        json={
            "name": "Bad",
            "steps": [{"id": "s1", "type": "exec_shell_command", "config": {}}],
        },
    )
    assert bad_resp.status_code == 422
