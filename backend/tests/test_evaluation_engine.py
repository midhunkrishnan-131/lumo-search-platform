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


def test_research_agent_evaluator_valid_invalid_and_failure(eval_client: TestClient):
    from app.models.research import ResearchSession

    # Invalid research dataset (missing question/topic) -> 400
    bad_ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={"name": "Bad Research", "category": "research", "cases": [{"note": "no question"}]},
    ).json()
    bad_bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "Bad Research BM", "category": "research", "dataset_id": bad_ds["id"], "target_module": "research_agent"},
    ).json()
    bad_run = eval_client.post(f"/api/v1/evaluations/{bad_bm['id']}/run", json={})
    assert bad_run.status_code == 400

    # Valid research dataset with 2 cases (1 completed, 1 failed)
    good_ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "Good Research",
            "category": "research",
            "cases": [
                {
                    "id": "r1",
                    "question": "Compare Hybrid Search and Classic Search",
                    "expected_sections": ["Summary", "Findings"],
                    "expected_source_urls": ["https://docs.lumo.local/hybrid"],
                    "max_iterations": 1,
                },
                {"id": "r2", "question": "Simulated failing research task"},
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "Research BM", "category": "research", "dataset_id": good_ds["id"], "target_module": "research_agent"},
    ).json()

    call_idx = {"n": 0}

    def _mock_start(session_id: str, background: bool = False):
        call_idx["n"] += 1
        with get_session_factory()() as db:
            s = db.query(ResearchSession).filter(ResearchSession.id == session_id).first()
            if call_idx["n"] == 1:
                s.status = "completed"
                s.sources = [
                    {"source_id": "S1", "url": "https://docs.lumo.local/hybrid"},
                    {"source_id": "S2", "url": "https://arxiv.org/abs/1234"},
                ]
                s.report_markdown = "## Summary\nHybrid combines BM25 and vectors [S1].\n## Findings\nImproves recall [S2]."
            else:
                s.status = "failed"
                s.sources = []
                s.report_markdown = ""
            db.commit()
            db.refresh(s)
            return s

    with patch("app.evaluation.runner.research_manager.start_session", side_effect=_mock_start):
        run = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={"provider": "auto"})
    assert run.status_code == 200
    body = run.json()
    assert body["passed_cases"] == 1
    assert body["failed_cases"] == 1
    assert body["metrics_json"]["completion_rate"] == 0.5
    assert body["metrics_json"]["avg_source_diversity"] == 1.0
    assert body["metrics_json"]["citation_validity_rate"] == 1.0
    assert body["metrics_json"]["reference_source_hit_rate"] == 1.0


def test_real_benchmark_cancellation_before_and_during_execution(eval_client: TestClient):
    from app.evaluation.runner import EvaluationManager, _CANCELLED_RUNS

    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "Cancel Suite",
            "category": "guardian",
            "cases": [
                {"id": "c1", "url": "http://127.0.0.1/a", "expected_blocked": True},
                {"id": "c2", "url": "http://127.0.0.1/b", "expected_blocked": True},
                {"id": "c3", "url": "http://127.0.0.1/c", "expected_blocked": True},
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "Cancel BM", "category": "guardian", "dataset_id": ds["id"], "target_module": "guardian"},
    ).json()

    # 1. Cancel mid-execution after case 1
    calls = {"n": 0}
    orig_is_cancelled = EvaluationManager._is_cancelled

    def _cancel_after_one(self, run_id: str) -> bool:
        calls["n"] += 1
        # Check #1 is pre-loop, #2 is before c1, #3 is before c2 -> trigger cancel!
        if calls["n"] == 3:
            self.cancel_run(run_id)
        return orig_is_cancelled(self, run_id)

    with patch.object(EvaluationManager, "_is_cancelled", _cancel_after_one):
        run = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={}).json()

    assert run["status"] == "cancelled"
    assert run["passed_cases"] == 1
    assert run["total_cases"] == 3
    assert run["metrics_json"]["cancelled"] is True
    assert run["id"] not in _CANCELLED_RUNS

    # Detail results preserved only for c1
    details = eval_client.get(f"/api/v1/evaluations/runs/{run['id']}/results").json()
    assert len(details["results_json"]) == 1
    assert details["results_json"][0]["case_id"] == "c1"

    # 2. Cancel before execution (0 cases run)
    with patch.object(EvaluationManager, "_is_cancelled", return_value=True):
        pre_cancel = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={}).json()
    assert pre_cancel["status"] == "cancelled"
    assert pre_cancel["passed_cases"] == 0
    assert pre_cancel["id"] not in _CANCELLED_RUNS


def test_dataset_import_formats_invalid_and_oversized(eval_client: TestClient):
    # JSON import
    r_json = eval_client.post(
        "/api/v1/evaluation-datasets/import",
        data={"name": "JSON Import", "category": "guardian", "version": "1.0"},
        files={"file": ("suite.json", b'[{"url": "http://127.0.0.1/x", "expected_blocked": true}]', "application/json")},
    )
    assert r_json.status_code == 201
    assert r_json.json()["format_type"] == "json"

    # JSONL import
    r_jsonl = eval_client.post(
        "/api/v1/evaluation-datasets/import",
        data={"name": "JSONL Import", "category": "data_intelligence", "version": "1.0"},
        files={"file": ("suite.jsonl", b'{"values": [1, 3], "expected_mean": 2.0}\n', "application/x-ndjson")},
    )
    assert r_jsonl.status_code == 201
    assert r_jsonl.json()["format_type"] == "jsonl"

    # Invalid empty file -> 400
    r_empty = eval_client.post(
        "/api/v1/evaluation-datasets/import",
        data={"name": "Empty", "category": "search"},
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r_empty.status_code == 400

    # Oversized > 5 MB -> 400
    big_bytes = b"a" * (5 * 1024 * 1024 + 10)
    r_big = eval_client.post(
        "/api/v1/evaluation-datasets/import",
        data={"name": "Too Big", "category": "search"},
        files={"file": ("big.json", big_bytes, "application/json")},
    )
    assert r_big.status_code == 400


def test_human_reviews_and_model_provider_comparison(eval_client: TestClient):
    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={"name": "Model Cmp DS", "category": "data_intelligence", "cases": [{"values": [2, 4], "expected_mean": 3.0}]},
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "Model Cmp BM", "category": "data_intelligence", "dataset_id": ds["id"], "target_module": "data_intelligence"},
    ).json()

    run_a = eval_client.post(
        f"/api/v1/evaluations/{bm['id']}/run",
        json={"k": 5, "provider": "gemini", "model_name": "gemini-1.5-flash"},
    ).json()
    run_b = eval_client.post(
        f"/api/v1/evaluations/{bm['id']}/run",
        json={"k": 5, "provider": "grok", "model_name": "grok-beta"},
    ).json()

    assert run_a["provider_name"] == "gemini"
    assert run_a["model_name"] == "gemini-1.5-flash"
    assert run_b["provider_name"] == "grok"
    assert run_b["model_name"] == "grok-beta"

    # Compare two model runs
    cmp_res = eval_client.get(f"/api/v1/evaluations/compare?baseline_run_id={run_a['id']}&current_run_id={run_b['id']}")
    assert cmp_res.status_code == 200
    assert "metric_deltas" in cmp_res.json()

    # Human review validation (score 6 -> 422), persistence, retrieval, and 404 on unknown run
    bad_rev = eval_client.post(f"/api/v1/evaluations/runs/{run_a['id']}/reviews", json={"score": 6, "status": "approved"})
    assert bad_rev.status_code == 422

    ok_rev = eval_client.post(
        f"/api/v1/evaluations/runs/{run_a['id']}/reviews",
        json={"case_id": "data_1", "score": 4, "reviewer_notes": "Accurate mean calculation.", "status": "approved"},
    )
    assert ok_rev.status_code == 201

    revs = eval_client.get(f"/api/v1/evaluations/runs/{run_a['id']}/reviews")
    assert revs.status_code == 200
    assert len(revs.json()) == 1
    assert revs.json()[0]["reviewer_notes"] == "Accurate mean calculation."

    miss_rev = eval_client.post("/api/v1/evaluations/runs/nonexistent/reviews", json={"score": 3, "status": "flagged"})
    assert miss_rev.status_code == 404


def test_ai_search_reference_answer_and_optional_llm_judge(eval_client: TestClient):
    from app.evaluation.metrics import evaluate_reference_answer

    # Unit checks for reference answer metrics
    assert evaluate_reference_answer("anything", None) is None
    empty_pred = evaluate_reference_answer("", "FastAPI is a Python framework")
    assert empty_pred["token_f1"] == 0.0
    exact = evaluate_reference_answer("FastAPI is a Python framework [S1].", "FastAPI is a Python framework")
    assert exact["exact_match"] == 1.0
    assert exact["token_f1"] == 1.0

    # Seed doc for AISearchOrchestrator
    with get_session_factory()() as db:
        db.add(
            Document(
                id="eval-ai-ref-1",
                url="https://lumo.local/fastapi-ref",
                title="FastAPI Overview",
                main_content="FastAPI is a modern Python web framework.",
                content_hash="hevalairef1",
                extraction_status="completed",
                is_duplicate=False,
            )
        )
        db.commit()

    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "AI Ref + Judge",
            "category": "ai_search",
            "cases": [
                {
                    "id": "q_ref",
                    "question": "What is FastAPI?",
                    "reference_answer": "FastAPI is a modern Python web framework.",
                },
                {
                    "id": "q_noref",
                    "question": "What is FastAPI?",
                },
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "AI Judge BM", "category": "ai_search", "dataset_id": ds["id"], "target_module": "ai_search"},
    ).json()

    ans_resp = AIProviderResponse(content="FastAPI is a modern Python web framework [S1].", provider="gemini", model="gemini-1.5-flash")
    judge_resp = AIProviderResponse(
        content='{"relevance": 5, "completeness": 4, "grounding": 5, "clarity": 5}',
        provider="grok",
        model="grok-beta",
    )

    with patch("app.ai.router.AIProviderRouter.execute", side_effect=[
        (ans_resp, False, "gemini"),
        (judge_resp, False, "grok"),
        (ans_resp, False, "gemini"),
        RuntimeError("Judge provider timeout"),
    ]):
        run = eval_client.post(
            f"/api/v1/evaluations/{bm['id']}/run",
            json={"use_llm_judge": True, "judge_provider": "grok", "judge_model": "grok-beta"},
        )
    assert run.status_code == 200
    m = run.json()["metrics_json"]
    assert m["token_f1"] == 1.0
    assert m["exact_match"] == 1.0
    assert m["llm_judge_scores"]["is_estimate"] is True
    assert m["llm_judge_scores"]["relevance"] == 5.0
    assert m["llm_judge_scores"]["judge_provider"] == "grok"


def test_knowledge_graph_relationship_and_evidence_evaluation(eval_client: TestClient):
    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "KG Rel Eval",
            "category": "knowledge_graph",
            "cases": [
                {
                    "id": "kg_rel_1",
                    "text": "FastAPI uses PostgreSQL for backend storage.",
                    "expected_entities": ["fastapi", "postgresql"],
                    "expected_relationships": [
                        {"source": "FastAPI", "type": "USES", "target": "PostgreSQL"},
                    ],
                },
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={"name": "KG Rel BM", "category": "knowledge_graph", "dataset_id": ds["id"], "target_module": "knowledge_graph"},
    ).json()
    run = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={})
    assert run.status_code == 200
    m = run.json()["metrics_json"]
    assert m["entity_f1"] > 0.0
    assert m["relationship_f1_normalized"] == 1.0
    assert m["relationship_f1_exact"] == 1.0
    assert m["evidence_attribution_rate"] == 1.0


def test_data_intelligence_profile_chart_and_edge_cases(eval_client: TestClient):
    csv_sample = "category,score\nalpha,10\nbeta,20\nalpha,\n"
    json_sample = '[{"item": "a", "val": 2.5}, {"item": "b", "val": 7.5}]'
    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "Data Intelligence Expanded",
            "category": "data_intelligence",
            "cases": [
                {
                    "id": "di_csv_profile_chart",
                    "csv_content": csv_sample,
                    "expected_profile": {
                        "row_count": 3,
                        "column_count": 2,
                        "column_names": ["category", "score"],
                        "column_types": {"category": "categorical", "score": "integer"},
                        "total_missing_cells": 1,
                        "missing_values": {"score": 1},
                        "numeric_stats": {"score": {"mean": 15.0, "min": 10.0, "max": 20.0}},
                        "categorical_stats": {"category": "alpha"},
                    },
                    "chart": {"chart_type": "bar", "x_column": "category", "y_column": "score"},
                    "expected_chart": {
                        "chart_type": "bar",
                        "x_label": "category",
                        "min_labels": 2,
                    },
                },
                {
                    "id": "di_json_profile",
                    "json_content": json_sample,
                    "expected_profile": {
                        "row_count": 2,
                        "column_count": 2,
                        "numeric_stats": {"val": {"mean": 5.0}},
                    },
                },
                {
                    "id": "di_empty_chart_error",
                    "csv_content": "",
                    "chart": {"chart_type": "bar"},
                    "expect_error": True,
                },
                {
                    "id": "di_legacy_numeric",
                    "values": [10, 20, 30],
                    "expected_mean": 20.0,
                },
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Data Intelligence Expanded BM",
            "category": "data_intelligence",
            "dataset_id": ds["id"],
            "target_module": "data_intelligence",
        },
    ).json()
    run = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={})
    assert run.status_code == 200
    body = run.json()
    assert body["passed_cases"] == 4
    assert body["failed_cases"] == 0
    assert body["metrics_json"]["numeric_accuracy"] == 1.0
    assert body["metrics_json"]["profile_accuracy"] == 1.0
    assert body["metrics_json"]["chart_accuracy"] == 1.0


def test_guardian_url_and_file_analyzer_evaluation(eval_client: TestClient):
    import base64

    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR").decode("ascii")
    spoof_pdf_b64 = base64.b64encode(b"MZ" + b"\x00" * 64).decode("ascii")
    bad_zip_b64 = base64.b64encode(b"PK\x03\x04corrupted_zip_payload").decode("ascii")

    ds = eval_client.post(
        "/api/v1/evaluation-datasets",
        json={
            "name": "Guardian Expanded",
            "category": "guardian",
            "cases": [
                {
                    "id": "g_valid_png",
                    "filename": "icon.png",
                    "file_bytes_b64": png_b64,
                    "expected_format": "PNG Image",
                    "expected_mime": "image/png",
                    "forbidden_indicators": ["Mismatch"],
                },
                {
                    "id": "g_spoofed_pdf",
                    "filename": "invoice.pdf",
                    "file_bytes_b64": spoof_pdf_b64,
                    "expected_format": "Windows PE Executable / DLL",
                    "expected_min_findings": 1,
                    "expected_indicators": ["Mismatch"],
                },
                {
                    "id": "g_script_indicator",
                    "filename": "benign_test.ps1",
                    "file_text": "# synthetic test fixture\nInvoke-Expression 'Write-Output ok'\n",
                    "expected_indicators": ["Invoke-Expression"],
                },
                {
                    "id": "g_corrupt_zip",
                    "filename": "archive.zip",
                    "file_bytes_b64": bad_zip_b64,
                    "expected_indicators": ["Corrupted"],
                },
                {
                    "id": "g_url_ssrf",
                    "url": "http://127.0.0.1/admin",
                    "expected_blocked": True,
                    "expected_valid": False,
                    "expected_indicators": ["private"],
                },
                {
                    "id": "g_url_public",
                    "url": "https://example.com/report.pdf",
                    "expected_blocked": False,
                    "expected_valid": True,
                },
            ],
        },
    ).json()
    bm = eval_client.post(
        "/api/v1/evaluations",
        json={
            "name": "Guardian Expanded BM",
            "category": "guardian",
            "dataset_id": ds["id"],
            "target_module": "guardian",
        },
    ).json()
    run = eval_client.post(f"/api/v1/evaluations/{bm['id']}/run", json={})
    assert run.status_code == 200
    body = run.json()
    assert body["passed_cases"] == 6
    assert body["failed_cases"] == 0
    assert body["metrics_json"]["rule_accuracy"] == 1.0
    assert body["metrics_json"]["url_accuracy"] == 1.0
    assert body["metrics_json"]["file_analysis_accuracy"] == 1.0
