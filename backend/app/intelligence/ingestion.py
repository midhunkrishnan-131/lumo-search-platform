"""Universal Data Ingestion & Processing Pipeline (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.graph.extractor import EntityExtractor
from app.graph.service import invalidate_graph_cache
from app.intelligence.classifier import classify_content
from app.intelligence.security import (
    SUPPORTED_IMAGE_EXTS,
    SUPPORTED_SPREADSHEET_EXTS,
    SUPPORTED_STRUCTURED_EXTS,
    redact_secrets,
    save_dataset_blob,
    sha256_bytes,
    validate_file_upload,
)
from app.intelligence.spreadsheet import profile_dataset_file
from app.models.graph import Entity, EntityDocument
from app.models.intelligence import UniversalDataset, UniversalImportJob
from app.models.workspace import WorkspaceItem
from app.workspace.importer import WorkspaceImporter, _make_summary, compute_content_hash

logger = get_logger("intelligence.ingestion")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_image_metadata_and_ocr(data: bytes, ext: str, safe_name: str) -> tuple[str, dict[str, Any]]:
    """Extract image dimensions safely and run optional local Tesseract OCR if installed."""
    width, height = None, None
    try:
        if ext == ".png" and len(data) >= 24:
            width, height = struct.unpack(">II", data[16:24])
        elif ext == ".webp" and len(data) >= 30 and data[12:16] == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif ext in (".jpg", ".jpeg"):
            idx = 2
            while idx + 9 < len(data):
                if data[idx] != 0xFF:
                    break
                marker = data[idx + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    height, width = struct.unpack(">HH", data[idx + 5 : idx + 9])
                    break
                seg_len = int.from_bytes(data[idx + 2 : idx + 4], "big")
                if seg_len < 2:
                    break
                idx += 2 + seg_len
    except Exception:
        pass

    ocr_text = ""
    ocr_engine = None
    tess = shutil.which("tesseract")
    if tess:
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                proc = subprocess.run(
                    [tess, tmp.name, "stdout", "--psm", "3"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    ocr_text = proc.stdout.strip()
                    ocr_engine = "tesseract"
        except Exception as exc:
            logger.debug("Optional local OCR skipped (%s)", type(exc).__name__)

    dim_str = f"{width}x{height}" if (width and height) else "unknown dimensions"
    meta = {
        "image_width": width,
        "image_height": height,
        "ocr_engine": ocr_engine,
        "has_ocr_text": bool(ocr_text),
    }
    if ocr_text:
        content = f"Image '{safe_name}' ({dim_str}) OCR Text:\n\n{ocr_text}"
    else:
        content = (
            f"Image file '{safe_name}' ({ext.lstrip('.').upper()}, {dim_str}, {len(data)} bytes). "
            "Metadata indexed locally."
        )
    return content, meta


class UniversalIngestionPipeline:
    """Coordinates staged ingestion, profiling, classification, Workspace storage, and Graph linking."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.workspace_importer = WorkspaceImporter()
        self.entity_extractor = EntityExtractor()

    @staticmethod
    def recover_interrupted_jobs(db: Session) -> int:
        """Mark in-flight ingestion jobs interrupted by server restart as retryable failures."""
        active_states = ("pending", "validating", "extracting", "classifying", "indexing")
        stuck = db.query(UniversalImportJob).filter(UniversalImportJob.status.in_(active_states)).all()
        for job in stuck:
            job.status = "failed"
            job.error_message = "Interrupted by server restart; ready to retry."
            job.updated_at = utc_now()
        if stuck:
            db.commit()
        return len(stuck)

    def _update_stage(self, job: UniversalImportJob, status: str, stage: str, progress: int) -> None:
        job.status = status
        job.current_stage = stage
        job.progress_pct = progress
        job.updated_at = utc_now()
        self.db.commit()

    def _link_knowledge_graph(self, title: str, text: str, item_id: str) -> int:
        """Extract entities from ingested content and upsert into Knowledge Graph safely."""
        if not text or not text.strip():
            return 0
        extracted = self.entity_extractor.extract(f"{title}\n{text[:15000]}", max_entities=20)
        linked = 0
        for ent in extracted:
            existing = (
                self.db.query(Entity)
                .filter(Entity.normalized_name == ent.normalized_name)
                .first()
            )
            if not existing:
                existing = Entity(
                    id=str(uuid.uuid4()),
                    name=ent.name,
                    normalized_name=ent.normalized_name,
                    entity_type=ent.entity_type,
                    confidence=ent.confidence,
                    extraction_method="universal_ingestion",
                )
                self.db.add(existing)
                self.db.flush()
            else:
                existing.updated_at = utc_now()
            linked += 1
        if linked:
            invalidate_graph_cache()
        return linked

    def ingest_file(
        self,
        filename: str,
        data: bytes,
        collection_id: str | None = None,
        classify_with_ai: bool = False,
        provider: str = "auto",
    ) -> UniversalImportJob:
        """Run the full staged Universal Processing Pipeline for an uploaded file."""
        job = UniversalImportJob(
            id=str(uuid.uuid4()),
            source_kind="file",
            file_name=Path(filename or "upload").name[:255],
            file_size_bytes=len(data or b""),
            status="validating",
            current_stage="file_validation",
            progress_pct=10,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        try:
            safe_name, ext = validate_file_upload(filename, data)
            fmt = ext.lstrip(".")
            job.file_name = safe_name
            job.format_type = fmt
            job.content_hash = sha256_bytes(data)

            self._update_stage(job, "extracting", "content_extraction", 35)

            is_tabular = ext in SUPPORTED_SPREADSHEET_EXTS or ext in SUPPORTED_STRUCTURED_EXTS
            dataset_obj: UniversalDataset | None = None
            extracted_meta: dict[str, Any] = {"size_bytes": len(data), "extension": ext}

            if is_tabular:
                ds_id = str(uuid.uuid4())
                blob_path = save_dataset_blob(ds_id, ext, data)
                prof = profile_dataset_file(blob_path, fmt)
                title = Path(safe_name).stem
                content = (
                    f"{prof['summary']}\n\n"
                    f"Columns: {', '.join(c['name'] + ' (' + c['inferred_type'] + ')' for c in prof['columns'])}\n\n"
                    f"Sample rows:\n{prof['preview_text']}"
                )
                summary = prof["summary"]
                extracted_meta.update(
                    {
                        "row_count": prof["row_count"],
                        "column_count": prof["column_count"],
                        "sheet_count": prof["sheet_count"],
                        "dataset_id": ds_id,
                    }
                )
                ws_item = WorkspaceItem(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=content,
                    summary=summary,
                    source_type="dataset",
                    file_name=safe_name,
                    file_type=fmt,
                    content_hash=compute_content_hash(content),
                    collection_id=collection_id,
                    metadata_json=extracted_meta,
                )
                self.db.add(ws_item)
                self.db.flush()

                dataset_obj = UniversalDataset(
                    id=ds_id,
                    workspace_item_id=ws_item.id,
                    title=title,
                    file_name=safe_name,
                    file_type=fmt,
                    row_count=prof["row_count"],
                    column_count=prof["column_count"],
                    sheet_count=prof["sheet_count"],
                    sheet_names=prof["sheet_names"],
                    active_sheet=prof["active_sheet"],
                    columns_json=prof["columns"],
                    profile_json=prof["profile"],
                    summary=summary,
                    storage_path=str(blob_path),
                )
                self.db.add(dataset_obj)
                self.db.flush()
                job.dataset_id = dataset_obj.id

            elif ext in SUPPORTED_IMAGE_EXTS:
                title = Path(safe_name).stem
                content, img_meta = _extract_image_metadata_and_ocr(data, ext, safe_name)
                extracted_meta.update(img_meta)
                summary = _make_summary(content)
                ws_item = WorkspaceItem(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=content,
                    summary=summary,
                    source_type="image",
                    file_name=safe_name,
                    file_type=fmt,
                    content_hash=compute_content_hash(content),
                    collection_id=collection_id,
                    metadata_json=extracted_meta,
                )
                self.db.add(ws_item)
                self.db.flush()
            else:
                # Reuse WorkspaceImporter for PDF, DOCX, TXT, MD, HTML
                payload = self.workspace_importer.import_bytes(safe_name, data)
                title = payload.title
                content = payload.content
                summary = payload.summary
                extracted_meta.update(payload.metadata)
                ws_item = WorkspaceItem(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=content,
                    summary=summary,
                    source_type="document",
                    file_name=payload.file_name,
                    file_type=payload.file_type,
                    content_hash=payload.content_hash,
                    collection_id=collection_id,
                    metadata_json=extracted_meta,
                )
                self.db.add(ws_item)
                self.db.flush()

            # Stage: Classification
            self._update_stage(job, "classifying", "content_classification", 65)
            cls_info = classify_content(
                title=title,
                text=content,
                file_type=fmt,
                format_kind="dataset" if is_tabular else "document",
                use_ai=classify_with_ai,
                provider=provider,
            )
            job.content_category = cls_info["category"]
            extracted_meta["classification"] = cls_info
            extracted_meta["word_count"] = len(content.split())
            ws_item.metadata_json = extracted_meta

            # Stage: Knowledge Graph linking
            self._update_stage(job, "indexing", "knowledge_graph_integration", 85)
            kg_linked = self._link_knowledge_graph(title, content, ws_item.id)
            extracted_meta["graph_entities_linked"] = kg_linked

            job.workspace_item_id = ws_item.id
            job.metadata_json = extracted_meta
            job.status = "completed"
            job.current_stage = "completed"
            job.progress_pct = 100
            job.completed_at = utc_now()
            self.db.commit()
            self.db.refresh(job)
            return job

        except Exception as exc:
            self.db.rollback()
            job.status = "failed"
            job.error_message = redact_secrets(str(exc))[:1000]
            job.updated_at = utc_now()
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            raise

    def ingest_url(
        self,
        url: str,
        title: str | None = None,
        collection_id: str | None = None,
        classify_with_ai: bool = False,
        provider: str = "auto",
    ) -> UniversalImportJob:
        """Ingest an SSRF-screened web URL into Universal Data Intelligence."""
        job = UniversalImportJob(
            id=str(uuid.uuid4()),
            source_kind="url",
            format_type="html",
            source_url=url,
            status="validating",
            current_stage="url_ssrf_validation",
            progress_pct=15,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        try:
            self._update_stage(job, "extracting", "web_extraction", 40)
            payload = self.workspace_importer.import_url(url, title_override=title)
            job.content_hash = payload.content_hash

            self._update_stage(job, "classifying", "content_classification", 70)
            cls_info = classify_content(
                title=payload.title,
                text=payload.content,
                file_type="html",
                format_kind="document",
                use_ai=classify_with_ai,
                provider=provider,
            )
            meta = dict(payload.metadata)
            meta["classification"] = cls_info
            meta["word_count"] = len(payload.content.split())

            ws_item = WorkspaceItem(
                id=str(uuid.uuid4()),
                title=payload.title,
                content=payload.content,
                summary=payload.summary,
                source_type="webpage",
                source_url=payload.source_url,
                file_type="html",
                content_hash=payload.content_hash,
                collection_id=collection_id,
                metadata_json=meta,
            )
            self.db.add(ws_item)
            self.db.flush()

            self._update_stage(job, "indexing", "knowledge_graph_integration", 90)
            meta["graph_entities_linked"] = self._link_knowledge_graph(payload.title, payload.content, ws_item.id)
            ws_item.metadata_json = meta

            job.workspace_item_id = ws_item.id
            job.content_category = cls_info["category"]
            job.metadata_json = meta
            job.status = "completed"
            job.current_stage = "completed"
            job.progress_pct = 100
            job.completed_at = utc_now()
            self.db.commit()
            self.db.refresh(job)
            return job
        except Exception as exc:
            self.db.rollback()
            job.status = "failed"
            job.error_message = redact_secrets(str(exc))[:1000]
            job.updated_at = utc_now()
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            raise

    def delete_import_job(self, job_id: str) -> bool:
        """Delete import job and synchronize deletion of linked dataset blob, dataset row, and workspace item."""
        job = self.db.query(UniversalImportJob).filter(UniversalImportJob.id == job_id).first()
        if not job:
            return False

        ds_id = job.dataset_id
        ws_id = job.workspace_item_id

        if ds_id:
            ds = self.db.query(UniversalDataset).filter(UniversalDataset.id == ds_id).first()
            if ds:
                if ds.storage_path:
                    try:
                        p = Path(ds.storage_path)
                        if p.exists():
                            p.unlink()
                    except OSError:
                        pass
                self.db.delete(ds)

        if ws_id:
            ws = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == ws_id).first()
            if ws:
                self.db.delete(ws)

        self.db.delete(job)
        self.db.commit()
        return True
