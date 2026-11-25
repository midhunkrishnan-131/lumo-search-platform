"""Deterministic tests for LUMO Phase 25: Intelligence Testing, Benchmarking & Evaluation Engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.ai.base import AIProviderResponse
from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.evaluation.metrics import (
    average_precision,
    evaluate_citations,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.main import create_app
from app.models.document import Document
from app.models.evaluation import EvaluationRun


@pytest.fixture()
def eval_client(tmp_path: Path):
    db_path = tmp_path / "eval_test.db"
    cfg = Settings(environment="test", database_url=f"sqlite:///{db_path}", local_only_ai=False)
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


def test_ir_and_citation_metric_calculations():
    retrieved = ["d1", "d2", "d3", "d4"]
    grades = {"d1": 3.0, "d3": 1.0}
    assert precision_at_k(retrieved, grades, 2) == 0.5
    assert recall_at_k(retrieved, grades, 4) == 1.0
    assert reciprocal_rank(retrieved, grades) == 1.0
    assert average_precision(retrieved, grades) == pytest.approx(0.8333, abs=0.01)
    assert 0.8 <= ndcg_at_k(retrieved, grades, 4) <= 1.0

    cit = evaluate_citations("FastAPI is fast [1] and supports async [99].", {"1", "2"})
    assert cit["citations_found"] == 2
    assert cit["citation_validity_rate"] == 0.5
    assert cit["citation_coverage"] == 0.5
    assert cit["hallucinated_citations"] == ["99"]


def test_search_comparison_kg_doc_data_guardian_and_exports(eval_client: TestClient):
    # Seed indexed doc for search & AI search benchmarks
    with get_session_factory()() as db:
        db.add(
            Document(
                id="eval-doc-1",
                url="https://lumo.local/fastapi",
                title="FastAPI Guide",
                main_content="FastAPI is a Python web framework used with PostgreSQL.",
                content_hash="heval1",
                extraction_status="completed",
                is_duplicate=False,
            )
        )
        db.commit()

    # 1. Search comparison benchmark (Classic vs Semantic vs Hybrid)
    ds_search = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "Search Eval",
            "category": "search",
            "cases": [{"id": "q1", "query": "FastAPI", "relevant_grades": {"eval-doc-1": 2.0}}],
        },
    )
    assert ds_search.status_code == 201
    bm_search = eval_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Search Compare",
            "category": "search",
            "dataset_id": ds_search.json()["id"],
            "target_module": "search_comparison",
        },
    ).json()
    run_cmp = eval_client.post(f"/api/v1/evaluations/{bm_search['id']}/run", json={"k": 5})
    assert run_cmp.status_code == 200
    assert "classic_search" in run_cmp.json()["metrics_json"]["comparison"]

    # Export CSV & JSON
    run_id = run_cmp.json()["id"]
    assert eval_client.get(f"/api/v1/evaluations/runs/{run_id}/export?format=csv").status_code == 200
    assert eval_client.get(f"/api/v1/evaluations/runs/{run_id}/export?format=json").status_code == 200

    # Clone & cancel check
    cloned = eval_client.post(f"/api/v1/evaluations/{bm_search['id']}/clone")
    assert cloned.status_code == 201
    assert eval_client.post(f"/api/v1/evaluations/runs/{run_id}/cancel").status_code == 200

    # 2. Knowledge Graph benchmark
    ds_kg = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "KG Eval",
            "category": "knowledge_graph",
            "cases": [{"text": "FastAPI and PostgreSQL power LUMO.", "expected_entities": ["fastapi", "postgresql"]}],
        },
    ).json()
    bm_kg = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "KG Bench", "category": "knowledge_graph", "dataset_id": ds_kg["id"], "target_module": "knowledge_graph"},
    ).json()
    run_kg = eval_client.post(f"/api/v1/evaluations/{bm_kg['id']}/run", json={}).json()
    assert run_kg["metrics_json"]["entity_f1"] > 0.0

    # 3. Document Intelligence, Data Intelligence, Guardian benchmarks
    for cat, target, case in [
        ("document", "document_intelligence", {"title": "Invoice #1", "text": "Bill To: Acme\nAmount Due: $100", "expected_category": "invoice", "expected_substring": "Acme"}),
        ("data_intelligence", "data_intelligence", {"values": [10, 20, 30], "expected_mean": 20.0}),
        ("guardian", "guardian", {"url": "http://127.0.0.1/admin", "expected_blocked": True}),
    ]:
        ds = eval_client.post("/api/v1/evaluation-datasets", json={"name": cat, "category": cat, "cases": [case]}).json()
        bm = eval_client.post("/api/v1/evaluations", json={"name": f"{cat}_bm", "category": cat, "dataset_id": ds["id"], "target_module": target}).json()
        r = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={}).json()
        assert r["passed_cases"] == 1

    # 4. AI Search benchmark with mocked AIProviderRouter
    ds_ai = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={"name": "AI Eval", "category": "ai_search", "cases": [{"question": "What is FastAPI?"}]},
    ).json()
    bm_ai = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "AI Bench", "category": "ai_search", "dataset_id": ds_ai["id"], "target_module": "ai_search"},
    ).json()
    mock_resp = AIProviderResponse(content="FastAPI is a Python framework [S1].", provider="gemini", model="gemini-1.5-flash")
    with patch("app.ai.router.AIProviderRouter.execute", return_value=(mock_resp, False, "gemini")):
        run_ai = eval_client.post(f"/api/v1/evaluations/{bm_ai['id']}/run", json={}).json()
        assert run_ai["metrics_json"]["citation_validity_rate"] == 1.0

    # Human review
    rev = eval_client.post(
        f"/api/v1/evaluations/runs/{run_ai['id']}/reviews",
        json={"score": 5, "reviewer_notes": "Accurate citation.", "status": "approved"},
    )
    assert rev.status_code == 201


def test_regression_detection_and_dataset_import(eval_client: TestClient):
    # Import CSV dataset
    csv_bytes = b"query,relevant_ids\nLUMO,demo-1\n"
    imp = eval_client.post(
        "/api/v1/evaluation-datasets/import",
        data={"name": "CSV Bench", "category": "search"},
        files={"file": ("bench.csv", csv_bytes, "text/csv")},
    )
    assert imp.status_code == 201
    assert imp.json()["case_count"] == 1

    # Seed two runs to verify regression comparison
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "Reg Bench", "category": "search", "dataset_id": imp.json()["id"], "target_module": "classic_search"},
    ).json()
    with get_session_factory()() as db:
        db.add(EvaluationRun(id="run-base", benchmark_id=bm["id"], target_module="classic_search", status="completed", metrics_json={"recall@5": 0.90, "avg_ms": 10.0}))
        db.add(EvaluationRun(id="run-curr", benchmark_id=bm["id"], target_module="classic_search", status="completed", metrics_json={"recall@5": 0.70, "avg_ms": 30.0}))
        db.commit()

    cmp_res = eval_client.get("/api/v1/evaluations/compare?baseline_run_id=run-base&current_run_id=run-curr").json()
    assert cmp_res["regression_detected"] is True
    assert len(cmp_res["regressions"]) == 2
