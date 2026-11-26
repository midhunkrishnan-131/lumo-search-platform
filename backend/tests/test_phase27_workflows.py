"""Tests for LUMO Phase 27: Unified Intelligence Workspace & Orchestration."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import get_session_factory
from app.main import create_app
from app.models.document import Document
from app.workflows.router import WorkflowIntent, classify_and_plan


@pytest.fixture()
def wf_client(tmp_path: Path):
    db_file = tmp_path / "phase27_test.db"
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
                    id="wf-doc-1",
                    url="https://example.com/fastapi",
                    title="FastAPI Architecture",
                    main_content="FastAPI uses PostgreSQL and Pydantic for backend APIs.",
                    content_hash="hwfdoc1",
                    extraction_status="completed",
                    is_duplicate=False,
                )
            )
            db.commit()
        yield client


def test_deterministic_request_classification():
    assert classify_and_plan("fastapi tutorial")["intent"] == WorkflowIntent.SEARCH
    assert classify_and_plan("What is FastAPI?")["intent"] == WorkflowIntent.AI_SEARCH
    assert classify_and_plan("Verify URL http://127.0.0.1/admin")["intent"] == WorkflowIntent.URL_VERIFICATION
    assert classify_and_plan("Analyze dataset", inputs={"csv_content": "a,b\n1,2\n"})["intent"] == WorkflowIntent.DATA_ANALYSIS
    assert classify_and_plan("Inspect file", inputs={"filename": "a.png", "file_text": "hi"})["intent"] == WorkflowIntent.FILE_ANALYSIS
    multi = classify_and_plan(
        "Investigate https://example.com/fastapi and extract entities",
        inputs={"url": "https://example.com/fastapi", "document_text": "FastAPI uses PostgreSQL."},
    )
    assert multi["intent"] == WorkflowIntent.MULTI_MODULE_WORKFLOW
    assert "guardian_url" in multi["selected_modules"]
    assert "document_intelligence" in multi["selected_modules"]
    assert "knowledge_graph" in multi["selected_modules"]


def test_multi_module_workflow_plan_execute_export_and_history(wf_client: TestClient):
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR").decode("ascii")
    # 1. Create & Plan (does not auto-execute)
    create_resp = wf_client.post(
        "/api/v1/workflows",
        json={
            "user_request": "Verify http://127.0.0.1/test, analyze document and dataset for FastAPI",
            "preferred_intent": "MULTI_MODULE_WORKFLOW",
            "inputs": {
                "url": "http://127.0.0.1/test",
                "document_text": "FastAPI uses PostgreSQL for reliable persistence.",
                "csv_content": "category,score\nalpha,10\nbeta,20\n",
                "filename": "icon.png",
                "file_bytes_b64": png_b64,
            },
        },
    )
    assert create_resp.status_code == 201
    wf = create_resp.json()
    assert wf["status"] == "READY"
    assert wf["progress"] == 0.0

    # 2. Execute DAG (parallel wave 0 + dependent KG wave)
    exec_resp = wf_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={"search_mode": "classic"})
    assert exec_resp.status_code == 200
    done = exec_resp.json()
    assert done["status"] == "COMPLETED", done.get("errors_json")
    assert done["progress"] == 1.0
    assert "guardian_url" in done["results_json"]
    assert done["results_json"]["guardian_url"]["urls"][0]["is_blocked"] is True
    assert done["results_json"]["guardian_file"]["detected_format"] == "PNG Image"
    assert done["results_json"]["data_intelligence"]["profile"]["row_count"] == 2
    assert len(done["results_json"]["knowledge_graph"]["entities"]) >= 1
    assert any(d["type"] == "blocked_source" for d in done["disagreements_json"])

    # 3. Export Markdown & JSON
    md = wf_client.get(f"/api/v1/workflows/{wf['id']}/export?format=markdown")
    assert md.status_code == 200
    assert "LUMO Workflow Report" in md.text
    js = wf_client.get(f"/api/v1/workflows/{wf['id']}/export?format=json")
    assert js.status_code == 200
    assert js.json()["id"] == wf["id"]

    # 4. History search & filter
    hist = wf_client.get("/api/v1/workflows?intent=MULTI_MODULE_WORKFLOW&q=FastAPI")
    assert hist.status_code == 200
    assert len(hist.json()) == 1


def test_workflow_cancellation_isolation_and_permissions(wf_client: TestClient):
    # Owner A creates a workflow
    wf_a = wf_client.post(
        "/api/v1/workflows",
        headers={"X-LUMO-Owner": "alice"},
        json={"user_request": "fastapi search"},
    ).json()

    # Owner B cannot see or delete Alice's workflow
    assert wf_client.get(f"/api/v1/workflows/{wf_a['id']}", headers={"X-LUMO-Owner": "bob"}).status_code == 404
    assert wf_client.delete(f"/api/v1/workflows/{wf_a['id']}", headers={"X-LUMO-Owner": "bob"}).status_code == 404

    # Alice cancels before execution
    can = wf_client.post(f"/api/v1/workflows/{wf_a['id']}/cancel", headers={"X-LUMO-Owner": "alice"})
    assert can.status_code == 200
    assert can.json()["status"] == "CANCELLED"

    # API key permission check: read-only key cannot create/execute workflows
    ro_key = wf_client.post(
        "/api/v1/developer/keys",
        json={"name": "WFReadOnly", "permissions": ["workflows:read"]},
    ).json()["raw_key"]
    assert wf_client.get("/api/v1/workflows", headers={"X-API-Key": ro_key}).status_code == 200
    assert wf_client.post(
        "/api/v1/workflows",
        headers={"X-API-Key": ro_key},
        json={"user_request": "test"},
    ).status_code == 403


def test_workflow_resource_limit_and_partial_failure(wf_client: TestClient):
    oversized = "a,b\n" + ("1,2\n" * 600000)  # > 2 MB
    wf = wf_client.post(
        "/api/v1/workflows",
        json={"user_request": "analyze data", "inputs": {"csv_content": oversized}},
    ).json()
    res = wf_client.post(f"/api/v1/workflows/{wf['id']}/execute", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert len(body["errors_json"]) == 1
