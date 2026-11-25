"""FastAPI routes for LUMO Phase 18: Universal Data Intelligence Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.ai.router import AIProviderRouter
from app.database.connection import get_db
from app.intelligence.analyzer import UniversalAnalyzer
from app.intelligence.ingestion import UniversalIngestionPipeline
from app.intelligence.security import MAX_UPLOAD_BYTES, redact_secrets
from app.intelligence.spreadsheet import generate_chart_data, profile_dataset_file
from app.models.intelligence import (
    UniversalAnalysisReport,
    UniversalDataset,
    UniversalImportJob,
)
from app.models.workspace import WorkspaceItem
from app.schemas.intelligence import (
    AnalysisReportResponse,
    CrossAnalysisRequest,
    DatasetAnalyzeRequest,
    DatasetDetailResponse,
    DatasetSummaryResponse,
    DatasetVisualizeRequest,
    DocumentAnalyzeRequest,
    DocumentCompareRequest,
    DocumentDetailResponse,
    DocumentSummaryItem,
    ImportJobResponse,
    UrlImportRequest,
    VisualizationResponse,
)

router = APIRouter(prefix="/intelligence", tags=["universal-intelligence"])


@router.get("/providers/status")
def get_provider_status() -> dict[str, Any]:
    """Return safe AI provider configuration status without exposing API keys."""
    return AIProviderRouter().get_status()


@router.post("/import", response_model=ImportJobResponse, status_code=201)
async def import_file(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    title: str | None = Form(default=None),
    collection_id: str | None = Form(default=None),
    classify_with_ai: bool = Form(default=False),
    provider: str = Form(default="auto"),
    db: Session = Depends(get_db),
):
    pipeline = UniversalIngestionPipeline(db)
    try:
        if file is not None:
            data = await file.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum size limit ({MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
                )
            return pipeline.ingest_file(
                filename=file.filename or "upload",
                data=data,
                collection_id=collection_id or None,
                classify_with_ai=classify_with_ai,
                provider=provider,
            )
        if url:
            return pipeline.ingest_url(
                url=url,
                title=title,
                collection_id=collection_id or None,
                classify_with_ai=classify_with_ai,
                provider=provider,
            )
        raise HTTPException(status_code=400, detail="Provide either a file upload or a URL.")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc


@router.post("/import/url", response_model=ImportJobResponse, status_code=201)
def import_url_json(payload: UrlImportRequest, db: Session = Depends(get_db)):
    pipeline = UniversalIngestionPipeline(db)
    try:
        return pipeline.ingest_url(
            url=payload.url,
            title=payload.title,
            collection_id=payload.collection_id,
            classify_with_ai=payload.classify_with_ai,
            provider=payload.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc


@router.get("/imports", response_model=list[ImportJobResponse])
def list_imports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(UniversalImportJob)
    if status:
        q = q.filter(UniversalImportJob.status == status)
    return q.order_by(UniversalImportJob.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/imports/{import_id}", response_model=ImportJobResponse)
def get_import(import_id: str, db: Session = Depends(get_db)):
    job = db.query(UniversalImportJob).filter(UniversalImportJob.id == import_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found.")
    return job


@router.post("/imports/{import_id}/retry", response_model=ImportJobResponse)
def retry_import(import_id: str, db: Session = Depends(get_db)):
    job = db.query(UniversalImportJob).filter(UniversalImportJob.id == import_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found.")
    if job.source_kind == "url" and job.source_url:
        job.retry_count = (job.retry_count or 0) + 1
        db.commit()
        pipeline = UniversalIngestionPipeline(db)
        try:
            return pipeline.ingest_url(url=job.source_url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=redact_secrets(str(exc))) from exc
    if job.dataset_id:
        ds = db.query(UniversalDataset).filter(UniversalDataset.id == job.dataset_id).first()
        if ds and ds.storage_path and Path(ds.storage_path).exists():
            data = Path(ds.storage_path).read_bytes()
            job.retry_count = (job.retry_count or 0) + 1
            db.commit()
            return UniversalIngestionPipeline(db).ingest_file(ds.file_name or "dataset.csv", data)
    raise HTTPException(
        status_code=400,
        detail="Only URL imports or persisted dataset jobs can be retried automatically.",
    )


@router.delete("/imports/{import_id}")
def delete_import(import_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    deleted = UniversalIngestionPipeline(db).delete_import_job(import_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Import job not found.")
    return {"deleted": True}


# --- Documents ---


def _to_doc_summary(item: WorkspaceItem) -> DocumentSummaryItem:
    meta = item.metadata_json or {}
    cls_info = meta.get("classification") if isinstance(meta, dict) else {}
    category = cls_info.get("category", "general_document") if isinstance(cls_info, dict) else "general_document"
    words = meta.get("word_count") if isinstance(meta, dict) else None
    if words is None:
        words = len((item.content or "").split())
    return DocumentSummaryItem(
        id=item.id,
        title=item.title,
        source_type=item.source_type,
        file_name=item.file_name,
        file_type=item.file_type,
        content_category=category,
        summary=item.summary,
        word_count=int(words),
        created_at=item.created_at,
    )


@router.get("/documents", response_model=list[DocumentSummaryItem])
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WorkspaceItem)
        .order_by(WorkspaceItem.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_doc_summary(r) for r in rows]


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    item = db.query(WorkspaceItem).filter(WorkspaceItem.id == document_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Document not found.")
    base = _to_doc_summary(item)
    return DocumentDetailResponse(
        **base.model_dump(),
        content=item.content,
        source_url=item.source_url,
        metadata_json=item.metadata_json or {},
    )


@router.post("/documents/{document_id}/analyze", response_model=AnalysisReportResponse)
def analyze_document(
    document_id: str, payload: DocumentAnalyzeRequest, db: Session = Depends(get_db)
):
    try:
        return UniversalAnalyzer(db).analyze_document(
            document_id=document_id,
            mode=payload.mode,
            question=payload.question,
            provider=payload.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/documents/compare", response_model=AnalysisReportResponse)
def compare_documents(payload: DocumentCompareRequest, db: Session = Depends(get_db)):
    try:
        return UniversalAnalyzer(db).cross_analyze(
            source_ids=payload.document_ids,
            question=payload.question,
            report_type="comparison",
            provider=payload.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Datasets ---


@router.get("/datasets", response_model=list[DatasetSummaryResponse])
def list_datasets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return (
        db.query(UniversalDataset)
        .order_by(UniversalDataset.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.query(UniversalDataset).filter(UniversalDataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return ds


@router.get("/datasets/{dataset_id}/profile", response_model=DatasetDetailResponse)
def get_dataset_profile(
    dataset_id: str, sheet: str | None = Query(default=None), db: Session = Depends(get_db)
):
    ds = db.query(UniversalDataset).filter(UniversalDataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if sheet and ds.file_type == "xlsx" and ds.storage_path and Path(ds.storage_path).exists():
        prof = profile_dataset_file(Path(ds.storage_path), "xlsx", sheet_name=sheet)
        ds.active_sheet = prof["active_sheet"]
        ds.row_count = prof["row_count"]
        ds.column_count = prof["column_count"]
        ds.columns_json = prof["columns"]
        ds.profile_json = prof["profile"]
        ds.summary = prof["summary"]
        db.commit()
        db.refresh(ds)
    return ds


@router.post("/datasets/{dataset_id}/analyze", response_model=AnalysisReportResponse)
def analyze_dataset(
    dataset_id: str, payload: DatasetAnalyzeRequest, db: Session = Depends(get_db)
):
    try:
        return UniversalAnalyzer(db).analyze_dataset(
            dataset_id=dataset_id,
            question=payload.question,
            provider=payload.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/visualize", response_model=VisualizationResponse)
def visualize_dataset(
    dataset_id: str, payload: DatasetVisualizeRequest, db: Session = Depends(get_db)
):
    ds = db.query(UniversalDataset).filter(UniversalDataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if not ds.storage_path or not Path(ds.storage_path).exists():
        raise HTTPException(status_code=400, detail="Dataset source file is no longer available.")
    try:
        chart = generate_chart_data(
            path=Path(ds.storage_path),
            file_type=ds.file_type,
            columns_json=ds.columns_json or [],
            chart_type=payload.chart_type,
            x_column=payload.x_column,
            y_column=payload.y_column,
            limit=payload.limit,
            sheet_name=ds.active_sheet,
        )
        return VisualizationResponse(dataset_id=ds.id, **chart)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Cross-Document & Reports ---


@router.post("/cross-analysis", response_model=AnalysisReportResponse)
def cross_analysis(payload: CrossAnalysisRequest, db: Session = Depends(get_db)):
    try:
        return UniversalAnalyzer(db).cross_analyze(
            source_ids=payload.source_ids,
            question=payload.question,
            report_type="cross_document",
            provider=payload.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports", response_model=list[AnalysisReportResponse])
def list_reports(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return (
        db.query(UniversalAnalysisReport)
        .order_by(UniversalAnalysisReport.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/reports/{report_id}", response_model=AnalysisReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)):
    rep = db.query(UniversalAnalysisReport).filter(UniversalAnalysisReport.id == report_id).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    return rep
