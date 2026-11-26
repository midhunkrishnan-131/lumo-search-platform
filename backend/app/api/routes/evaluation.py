"""FastAPI routes for LUMO Phase 25: Intelligence Testing, Benchmarking & Evaluation Engine."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.evaluation.runner import EvaluationManager, parse_uploaded_dataset
from app.models.evaluation import EvaluationReview, EvaluationRun
from app.schemas.evaluation import (
    EvaluationBenchmarkCreate,
    EvaluationBenchmarkResponse,
    EvaluationBenchmarkUpdate,
    EvaluationDatasetCreate,
    EvaluationDatasetDetailResponse,
    EvaluationDatasetResponse,
    EvaluationReviewCreate,
    EvaluationReviewResponse,
    EvaluationRunDetailResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)

benchmarks_router = APIRouter(prefix="/evaluations", tags=["evaluation-benchmarks"])
datasets_router = APIRouter(prefix="/evaluation-datasets", tags=["evaluation-datasets"])


# --- Datasets ---


@datasets_router.get("", response_model=list[EvaluationDatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    return EvaluationManager(db).list_datasets()


@datasets_router.post("", response_model=EvaluationDatasetResponse, status_code=201)
def create_dataset(payload: EvaluationDatasetCreate, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).create_dataset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@datasets_router.post("/import", response_model=EvaluationDatasetResponse, status_code=201)
async def import_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(...),
    version: str = Form(default="1.0"),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
):
    raw = await file.read(5 * 1024 * 1024 + 1)
    try:
        fmt, cases = parse_uploaded_dataset(file.filename or "dataset.json", raw)
        return EvaluationManager(db).create_dataset(
            EvaluationDatasetCreate(
                name=name,
                description=description,
                category=category,
                version=version,
                cases=cases,
            ),
            format_type=fmt,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@datasets_router.get("/{dataset_id}", response_model=EvaluationDatasetDetailResponse)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).get_dataset(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@datasets_router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not EvaluationManager(db).delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Evaluation dataset not found.")
    return {"deleted": True}


# --- Benchmarks & Runs (static paths before /{benchmark_id}) ---


@benchmarks_router.get("", response_model=list[EvaluationBenchmarkResponse])
def list_benchmarks(db: Session = Depends(get_db)):
    return EvaluationManager(db).list_benchmarks()


@benchmarks_router.post("", response_model=EvaluationBenchmarkResponse, status_code=201)
def create_benchmark(payload: EvaluationBenchmarkCreate, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).create_benchmark(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@benchmarks_router.get("/runs", response_model=list[EvaluationRunResponse])
def list_runs(limit: int = Query(default=40, ge=1, le=200), db: Session = Depends(get_db)):
    return db.query(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(limit).all()


@benchmarks_router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run


@benchmarks_router.get("/runs/{run_id}/results", response_model=EvaluationRunDetailResponse)
def get_run_results(run_id: str, db: Session = Depends(get_db)):
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run


@benchmarks_router.get("/runs/{run_id}/export")
def export_run_report(run_id: str, format: str = Query(default="json"), db: Session = Depends(get_db)):
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    if format.lower() == "csv":
        buf = io.StringIO()
        rows = run.results_json or []
        fieldnames = sorted({k for r in rows if isinstance(r, dict) for k in r.keys()}) or ["case_id", "passed"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            if isinstance(r, dict):
                safe_row = {}
                for k in fieldnames:
                    v = r.get(k, "")
                    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
                        v = "'" + v
                    safe_row[k] = v
                writer.writerow(safe_row)
        return Response(content=buf.getvalue(), media_type="text/csv")
    return EvaluationRunDetailResponse.model_validate(run)


@benchmarks_router.post("/runs/{run_id}/cancel", response_model=EvaluationRunResponse)
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).cancel_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@benchmarks_router.post("/runs/{run_id}/reviews", response_model=EvaluationReviewResponse, status_code=201)
def add_review(run_id: str, payload: EvaluationReviewCreate, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).add_review(run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@benchmarks_router.get("/runs/{run_id}/reviews", response_model=list[EvaluationReviewResponse])
def list_reviews(run_id: str, db: Session = Depends(get_db)):
    return db.query(EvaluationReview).filter(EvaluationReview.run_id == run_id).order_by(EvaluationReview.created_at.desc()).all()


@benchmarks_router.get("/compare")
def compare_runs(
    baseline_run_id: str = Query(...),
    current_run_id: str = Query(...),
    regression_threshold: float = Query(default=0.05, ge=0.0, le=1.0),
    latency_threshold_pct: float = Query(default=50.0, ge=1.0, le=500.0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return EvaluationManager(db).compare_runs(
            baseline_run_id=baseline_run_id,
            current_run_id=current_run_id,
            regression_drop_threshold=regression_threshold,
            latency_increase_pct=latency_threshold_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@benchmarks_router.get("/{benchmark_id}", response_model=EvaluationBenchmarkResponse)
def get_benchmark(benchmark_id: str, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).get_benchmark(benchmark_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@benchmarks_router.put("/{benchmark_id}", response_model=EvaluationBenchmarkResponse)
def update_benchmark(benchmark_id: str, payload: EvaluationBenchmarkUpdate, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).update_benchmark(benchmark_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@benchmarks_router.post("/{benchmark_id}/clone", response_model=EvaluationBenchmarkResponse, status_code=201)
def clone_benchmark(benchmark_id: str, db: Session = Depends(get_db)):
    try:
        return EvaluationManager(db).clone_benchmark(benchmark_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@benchmarks_router.delete("/{benchmark_id}")
def delete_benchmark(benchmark_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not EvaluationManager(db).delete_benchmark(benchmark_id):
        raise HTTPException(status_code=404, detail="Benchmark not found.")
    return {"deleted": True}


@benchmarks_router.post("/{benchmark_id}/run", response_model=EvaluationRunResponse)
def run_benchmark(
    benchmark_id: str,
    payload: EvaluationRunRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        return EvaluationManager(db).run_benchmark(benchmark_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
