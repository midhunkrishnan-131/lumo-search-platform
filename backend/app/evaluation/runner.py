"""Evaluation Manager & Benchmark Runner for LUMO Phase 25."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import statistics
import threading
import time
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.ai.orchestrator import AISearchOrchestrator
from app.core.logging import get_logger
from app.evaluation.metrics import (
    average_precision,
    evaluate_citations,
    f1_score,
    get_process_memory_mb,
    latency_stats,
    ndcg_at_k,
    numeric_within_tolerance,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    set_prf1,
)
from app.graph.extractor import EntityExtractor
from app.guardian.validator import validate_guardian_url
from app.intelligence.classifier import classify_content_deterministic
from app.models.evaluation import (
    EvaluationBenchmark,
    EvaluationDataset,
    EvaluationReview,
    EvaluationRun,
)
from app.processor.extractor import extract_document_data
from app.schemas.ai import AISearchRequest
from app.schemas.evaluation import (
    EvaluationBenchmarkCreate,
    EvaluationBenchmarkUpdate,
    EvaluationDatasetCreate,
    EvaluationReviewCreate,
    EvaluationRunRequest,
)
from app.search.engine import ClassicSearchEngine
from app.search.hybrid import HybridSearchOrchestrator
from app.semantic.search import SemanticSearchEngine

logger = get_logger("evaluation.runner")

MAX_DATASET_CASES = 200
_CANCEL_LOCK = threading.Lock()
_CANCELLED_RUNS: set[str] = set()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_uploaded_dataset(filename: str, raw_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Validate and parse JSON, JSONL, or CSV evaluation datasets safely without executing anything."""
    if not raw_bytes:
        raise ValueError("Uploaded dataset is empty.")
    if len(raw_bytes) > 5 * 1024 * 1024:
        raise ValueError("Evaluation dataset exceeds 5 MB limit.")
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    lower = (filename or "").lower()

    if lower.endswith(".jsonl"):
        cases = [json.loads(line) for line in text.splitlines() if line.strip()]
        fmt = "jsonl"
    elif lower.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        cases = [dict(row) for row in reader]
        fmt = "csv"
    else:
        parsed = json.loads(text)
        cases = parsed if isinstance(parsed, list) else parsed.get("cases", [])
        fmt = "json"

    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must contain a non-empty list of test cases.")
    if len(cases) > MAX_DATASET_CASES:
        raise ValueError(f"Dataset exceeds maximum {MAX_DATASET_CASES} cases.")
    return fmt, cases


class EvaluationManager:
    """Coordinates evaluation datasets, benchmarks, execution, comparison, and regressions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Datasets ---

    def create_dataset(self, payload: EvaluationDatasetCreate, format_type: str = "json") -> EvaluationDataset:
        if len(payload.cases) > MAX_DATASET_CASES:
            raise ValueError(f"Dataset exceeds maximum {MAX_DATASET_CASES} cases.")
        ds = EvaluationDataset(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category,
            version=payload.version,
            format_type=format_type,
            case_count=len(payload.cases),
            cases_json=payload.cases,
            metadata_json=payload.metadata_json,
        )
        self.db.add(ds)
        self.db.commit()
        self.db.refresh(ds)
        return ds

    def list_datasets(self) -> list[EvaluationDataset]:
        return self.db.query(EvaluationDataset).order_by(EvaluationDataset.created_at.desc()).all()

    def get_dataset(self, dataset_id: str) -> EvaluationDataset:
        ds = self.db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
        if not ds:
            raise ValueError("Evaluation dataset not found.")
        return ds

    def delete_dataset(self, dataset_id: str) -> bool:
        ds = self.db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
        if not ds:
            return False
        self.db.delete(ds)
        self.db.commit()
        return True

    # --- Benchmarks ---

    def create_benchmark(self, payload: EvaluationBenchmarkCreate) -> EvaluationBenchmark:
        if payload.dataset_id:
            self.get_dataset(payload.dataset_id)
        bm = EvaluationBenchmark(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category,
            version=payload.version,
            dataset_id=payload.dataset_id,
            target_module=payload.target_module,
            config_json=payload.config_json,
            status="idle",
        )
        self.db.add(bm)
        self.db.commit()
        self.db.refresh(bm)
        return bm

    def list_benchmarks(self) -> list[EvaluationBenchmark]:
        return self.db.query(EvaluationBenchmark).order_by(EvaluationBenchmark.created_at.desc()).all()

    def get_benchmark(self, benchmark_id: str) -> EvaluationBenchmark:
        bm = self.db.query(EvaluationBenchmark).filter(EvaluationBenchmark.id == benchmark_id).first()
        if not bm:
            raise ValueError("Benchmark not found.")
        return bm

    def update_benchmark(self, benchmark_id: str, payload: EvaluationBenchmarkUpdate) -> EvaluationBenchmark:
        bm = self.get_benchmark(benchmark_id)
        if payload.name is not None:
            bm.name = payload.name.strip()
        if payload.description is not None:
            bm.description = payload.description
        if payload.dataset_id is not None:
            self.get_dataset(payload.dataset_id)
            bm.dataset_id = payload.dataset_id
        if payload.target_module is not None:
            bm.target_module = payload.target_module
        if payload.config_json is not None:
            bm.config_json = payload.config_json
        bm.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(bm)
        return bm

    def clone_benchmark(self, benchmark_id: str) -> EvaluationBenchmark:
        orig = self.get_benchmark(benchmark_id)
        clone = EvaluationBenchmark(
            id=str(uuid.uuid4()),
            name=f"{orig.name} (Copy)",
            description=orig.description,
            category=orig.category,
            version=orig.version,
            dataset_id=orig.dataset_id,
            target_module=orig.target_module,
            config_json=dict(orig.config_json or {}),
            status="idle",
        )
        self.db.add(clone)
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def delete_benchmark(self, benchmark_id: str) -> bool:
        bm = self.db.query(EvaluationBenchmark).filter(EvaluationBenchmark.id == benchmark_id).first()
        if not bm:
            return False
        self.db.delete(bm)
        self.db.commit()
        return True

    # --- Execution & Evaluators ---

    def cancel_run(self, run_id: str) -> EvaluationRun:
        run = self.db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
        if not run:
            raise ValueError("Evaluation run not found.")
        with _CANCEL_LOCK:
            _CANCELLED_RUNS.add(run_id)
        if run.status == "running":
            run.status = "cancelled"
            run.completed_at = utc_now()
            self.db.commit()
            self.db.refresh(run)
        return run

    def _run_search_mode(self, mode: str, query: str, k: int) -> list[str]:
        if mode == "classic_search":
            res = ClassicSearchEngine(self.db).search(query=query, page=1, per_page=k)
            return [r.id for r in res.results]
        if mode == "semantic_search":
            res = SemanticSearchEngine(self.db).search(query=query, page=1, per_page=k)
            return [r.id for r in res.results]
        res, _, _ = HybridSearchOrchestrator(self.db).search(query=query, page=1, per_page=k)
        return [r.id for r in res.results]

    def _evaluate_search_cases(self, mode: str, cases: list[dict[str, Any]], k: int) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
        precs, recs, f1s, mrrs, maps, ndcgs, lats = [], [], [], [], [], [], []
        case_results: list[dict[str, Any]] = []
        passed = 0
        failed = 0

        for idx, c in enumerate(cases):
            query = str(c.get("query") or "")
            raw_rel = c.get("relevant_grades") or c.get("relevant_ids") or []
            if isinstance(raw_rel, dict):
                grades = {str(dk): float(dv) for dk, dv in raw_rel.items()}
            else:
                grades = {str(did): 1.0 for did in raw_rel}

            t0 = time.perf_counter()
            try:
                retrieved = self._run_search_mode(mode, query, k)
                dur = round((time.perf_counter() - t0) * 1000, 2)
                lats.append(dur)
                p = precision_at_k(retrieved, grades, k)
                r = recall_at_k(retrieved, grades, k)
                f1 = f1_score(p, r)
                rr = reciprocal_rank(retrieved, grades)
                ap = average_precision(retrieved, grades)
                ndcg = ndcg_at_k(retrieved, grades, k)
                precs.append(p); recs.append(r); f1s.append(f1); mrrs.append(rr); maps.append(ap); ndcgs.append(ndcg)
                ok = r > 0 or not grades
                passed += 1 if ok else 0
                failed += 0 if ok else 1
                case_results.append({
                    "case_id": c.get("id", f"case_{idx+1}"),
                    "query": query,
                    "retrieved_ids": retrieved,
                    "precision": p,
                    "recall": r,
                    "ndcg": ndcg,
                    "latency_ms": dur,
                    "passed": ok,
                })
            except Exception as exc:
                failed += 1
                case_results.append({"case_id": c.get("id", f"case_{idx+1}"), "query": query, "passed": False, "error": str(exc)})

        metrics = {
            f"precision@{k}": round(statistics.fmean(precs), 4) if precs else 0.0,
            f"recall@{k}": round(statistics.fmean(recs), 4) if recs else 0.0,
            "f1": round(statistics.fmean(f1s), 4) if f1s else 0.0,
            "mrr": round(statistics.fmean(mrrs), 4) if mrrs else 0.0,
            "map": round(statistics.fmean(maps), 4) if maps else 0.0,
            f"ndcg@{k}": round(statistics.fmean(ndcgs), 4) if ndcgs else 0.0,
            **latency_stats(lats),
        }
        return metrics, case_results, passed, failed

    def run_benchmark(self, benchmark_id: str, req: EvaluationRunRequest | None = None) -> EvaluationRun:
        bm = self.get_benchmark(benchmark_id)
        if not bm.dataset_id:
            raise ValueError("Benchmark has no dataset assigned.")
        ds = self.get_dataset(bm.dataset_id)
        params = req or EvaluationRunRequest()
        cases = (ds.cases_json or [])[: params.max_cases]

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            benchmark_id=bm.id,
            dataset_version=ds.version,
            target_module=bm.target_module,
            model_name=params.model_name,
            provider_name=params.provider,
            status="running",
            total_cases=len(cases),
            config_json={"k": params.k, "max_cases": params.max_cases},
            started_at=utc_now(),
        )
        bm.status = "running"
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        t_start_mem = get_process_memory_mb()
        passed = 0
        failed = 0
        results: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}

        try:
            target = bm.target_module
            if target in ("classic_search", "semantic_search", "hybrid_search"):
                metrics, results, passed, failed = self._evaluate_search_cases(target, cases, params.k)
            elif target == "search_comparison":
                comp: dict[str, Any] = {}
                for mode in ("classic_search", "semantic_search", "hybrid_search"):
                    m_met, _, m_pass, m_fail = self._evaluate_search_cases(mode, cases, params.k)
                    comp[mode] = m_met
                    passed += m_pass
                    failed += m_fail
                metrics = {"comparison": comp}
                results = [{"mode": k_m, **v_m} for k_m, v_m in comp.items()]
            elif target == "ai_search":
                lats, valid_rates, covs = [], [], []
                orch = AISearchOrchestrator(self.db)
                for idx, c in enumerate(cases):
                    q = str(c.get("question") or c.get("query") or "")
                    t0 = time.perf_counter()
                    ai_res = orch.search(AISearchRequest(query=q, provider=params.provider))
                    lats.append(round((time.perf_counter() - t0) * 1000, 2))
                    valid_keys = {str(src.source_id) for src in (ai_res.sources or [])}
                    if not valid_keys:
                        valid_keys = {str(cit.source_id) for cit in (ai_res.citations or [])}
                    cit_eval = evaluate_citations(ai_res.answer, valid_keys)
                    valid_rates.append(cit_eval["citation_validity_rate"])
                    covs.append(cit_eval["citation_coverage"])
                    ok = cit_eval["citation_validity_rate"] >= 0.5
                    passed += 1 if ok else 0
                    failed += 0 if ok else 1
                    results.append({"case_id": c.get("id", f"ai_{idx+1}"), "status": getattr(ai_res, "status", "ok"), **cit_eval, "passed": ok})
                metrics = {
                    "citation_validity_rate": round(statistics.fmean(valid_rates), 4) if valid_rates else 0.0,
                    "citation_coverage": round(statistics.fmean(covs), 4) if covs else 0.0,
                    **latency_stats(lats),
                }
            elif target == "knowledge_graph":
                extractor = EntityExtractor()
                f1s, precs, recs, lats = [], [], [], []
                for idx, c in enumerate(cases):
                    t0 = time.perf_counter()
                    ents = extractor.extract(str(c.get("text") or ""), max_entities=30)
                    lats.append(round((time.perf_counter() - t0) * 1000, 2))
                    pred = {e.normalized_name for e in ents}
                    exp = {str(x).strip().lower() for x in (c.get("expected_entities") or []) if str(x).strip()}
                    prf = set_prf1(pred, exp)
                    precs.append(prf["precision"]); recs.append(prf["recall"]); f1s.append(prf["f1"])
                    ok = prf["f1"] >= 0.5
                    passed += 1 if ok else 0
                    failed += 0 if ok else 1
                    results.append({"case_id": c.get("id", f"kg_{idx+1}"), **prf, "passed": ok})
                metrics = {
                    "entity_precision": round(statistics.fmean(precs), 4) if precs else 0.0,
                    "entity_recall": round(statistics.fmean(recs), 4) if recs else 0.0,
                    "entity_f1": round(statistics.fmean(f1s), 4) if f1s else 0.0,
                    **latency_stats(lats),
                }
            elif target == "document_intelligence":
                lats = []
                for idx, c in enumerate(cases):
                    t0 = time.perf_counter()
                    html = str(c.get("html") or "")
                    text = str(c.get("text") or "")
                    title = str(c.get("title") or "")
                    if html:
                        ext = extract_document_data(html, "https://eval.local/doc")
                        text = ext.main_content
                        title = title or ext.title
                    cat, _, _ = classify_content_deterministic(title, text, str(c.get("file_type") or "txt"))
                    lats.append(round((time.perf_counter() - t0) * 1000, 2))
                    exp_cat = c.get("expected_category")
                    exp_sub = str(c.get("expected_substring") or "")
                    ok = (not exp_cat or cat == exp_cat) and (not exp_sub or exp_sub.lower() in text.lower())
                    passed += 1 if ok else 0
                    failed += 0 if ok else 1
                    results.append({"case_id": c.get("id", f"doc_{idx+1}"), "predicted_category": cat, "passed": ok})
                metrics = {"extraction_accuracy": round(passed / max(len(cases), 1), 4), **latency_stats(lats)}
            elif target == "data_intelligence":
                lats = []
                for idx, c in enumerate(cases):
                    t0 = time.perf_counter()
                    vals = [float(v) for v in (c.get("values") or [])]
                    exp_mean = float(c.get("expected_mean", 0.0))
                    actual_mean = statistics.fmean(vals) if vals else 0.0
                    lats.append(round((time.perf_counter() - t0) * 1000, 2))
                    ok = numeric_within_tolerance(actual_mean, exp_mean, rel_tol=0.01)
                    passed += 1 if ok else 0
                    failed += 0 if ok else 1
                    results.append({"case_id": c.get("id", f"data_{idx+1}"), "actual_mean": actual_mean, "expected_mean": exp_mean, "passed": ok})
                metrics = {"numeric_accuracy": round(passed / max(len(cases), 1), 4), **latency_stats(lats)}
            elif target == "guardian":
                lats = []
                for idx, c in enumerate(cases):
                    t0 = time.perf_counter()
                    res = validate_guardian_url(str(c.get("url") or ""), resolve_dns=False)
                    lats.append(round((time.perf_counter() - t0) * 1000, 2))
                    exp_blocked = bool(c.get("expected_blocked", False))
                    ok = res.is_blocked == exp_blocked
                    passed += 1 if ok else 0
                    failed += 0 if ok else 1
                    results.append({"case_id": c.get("id", f"guard_{idx+1}"), "blocked": res.is_blocked, "expected_blocked": exp_blocked, "passed": ok})
                metrics = {"rule_accuracy": round(passed / max(len(cases), 1), 4), **latency_stats(lats)}
            else:
                raise ValueError(f"Unsupported evaluation target_module '{target}'.")

            t_end_mem = get_process_memory_mb()
            metrics["memory_rss_mb"] = t_end_mem
            metrics["memory_delta_mb"] = round(t_end_mem - t_start_mem, 2) if (t_end_mem and t_start_mem) else None
            metrics["error_rate"] = round(failed / max(passed + failed, 1), 4)

            run.status = "completed"
            run.passed_cases = passed
            run.failed_cases = failed
            run.metrics_json = metrics
            run.results_json = results
            run.completed_at = utc_now()
            bm.status = "completed"
            bm.last_run_at = utc_now()
            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.completed_at = utc_now()
            bm.status = "failed"
            self.db.commit()
            self.db.refresh(run)
            raise

    def compare_runs(
        self,
        baseline_run_id: str,
        current_run_id: str,
        regression_drop_threshold: float = 0.05,
        latency_increase_pct: float = 50.0,
    ) -> dict[str, Any]:
        """Compare two runs and flag metric regressions or latency spikes beyond thresholds."""
        base = self.db.query(EvaluationRun).filter(EvaluationRun.id == baseline_run_id).first()
        curr = self.db.query(EvaluationRun).filter(EvaluationRun.id == current_run_id).first()
        if not base or not curr:
            raise ValueError("Both baseline_run_id and current_run_id must exist.")

        b_m = base.metrics_json or {}
        c_m = curr.metrics_json or {}
        diffs: dict[str, float] = {}
        regressions: list[str] = []

        for k, bv in b_m.items():
            if isinstance(bv, (int, float)) and isinstance(c_m.get(k), (int, float)):
                cv = float(c_m[k])
                delta = round(cv - float(bv), 4)
                diffs[k] = delta
                if k in ("avg_ms", "p95_ms") and float(bv) > 0:
                    pct = ((cv - float(bv)) / float(bv)) * 100.0
                    if pct > latency_increase_pct:
                        regressions.append(f"Latency regression in '{k}': +{pct:.1f}% ({bv}ms -> {cv}ms)")
                elif k not in ("error_rate", "memory_rss_mb", "memory_delta_mb", "median_ms", "p99_ms", "throughput_qps"):
                    if delta < -abs(regression_drop_threshold):
                        regressions.append(f"Metric regression in '{k}': {delta:+.4f} ({bv} -> {cv})")

        return {
            "baseline_run_id": baseline_run_id,
            "current_run_id": current_run_id,
            "metric_deltas": diffs,
            "regression_detected": len(regressions) > 0,
            "regressions": regressions,
        }

    def add_review(self, run_id: str, payload: EvaluationReviewCreate) -> EvaluationReview:
        run = self.db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
        if not run:
            raise ValueError("Evaluation run not found.")
        rev = EvaluationReview(
            id=str(uuid.uuid4()),
            run_id=run_id,
            case_id=payload.case_id,
            score=payload.score,
            reviewer_notes=payload.reviewer_notes,
            status=payload.status,
        )
        self.db.add(rev)
        self.db.commit()
        self.db.refresh(rev)
        return rev
