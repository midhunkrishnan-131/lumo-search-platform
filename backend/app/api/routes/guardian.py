"""FastAPI routes for LUMO Phase 10: Download Guardian and Security Analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db
from app.guardian.explainer import guardian_explainer
from app.guardian.file_analyzer import FileSecurityAnalyzer
from app.guardian.network import SafeNetworkInspector
from app.guardian.reputation import reputation_provider
from app.guardian.risk import risk_engine
from app.guardian.url_analyzer import UrlStructureAnalyzer
from app.guardian.validator import validate_guardian_url
from app.models.guardian import GuardianAnalysis
from app.schemas.guardian import (
    FileAnalysisResponse,
    FileHashLookupRequest,
    GuardianFinding,
    GuardianHistoryItemResponse,
    GuardianHistoryListResponse,
    UrlAnalysisRequest,
    UrlAnalysisResponse,
)

logger = get_logger("api.guardian")

router = APIRouter(prefix="/guardian", tags=["guardian"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@router.post(
    "/url",
    response_model=UrlAnalysisResponse,
    summary="Defensive URL Security Analysis",
    description="Inspects URL structure, detects deceptive patterns, traces redirects safely, checks TLS metadata, and evaluates risk.",
)
def analyze_url_endpoint(
    request: UrlAnalysisRequest,
    db: Session = Depends(get_db),
) -> UrlAnalysisResponse:
    raw_url = request.url.strip()
    if not raw_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="URL cannot be empty.")

    # 1. URL Validation & SSRF Screening
    val_res = validate_guardian_url(raw_url, resolve_dns=request.check_network)
    analysis_id = str(uuid.uuid4())
    now = utc_now()

    if not val_res.is_valid:
        # SSRF or prohibited address blocked
        findings = [
            GuardianFinding(
                name="Target Blocked by SSRF Policy",
                description=val_res.error or "The target URL resolves to an internal, private, or prohibited address.",
                severity="critical",
                evidence=f"Target: {raw_url}, Resolved IPs: {val_res.resolved_ips}",
                recommendation="Do not proceed. Access to local and internal addresses is strictly forbidden.",
            )
        ]
        risk_level, risk_score, recs, limits = risk_engine.evaluate(
            findings,
            is_blocked=True,
        )
        record = GuardianAnalysis(
            id=analysis_id,
            analysis_type="url",
            target=raw_url,
            target_identifier=val_res.hostname or "blocked-host",
            risk_level=risk_level,
            risk_score=risk_score,
            findings=[f.model_dump() for f in findings],
            target_metadata={"resolved_ips": val_res.resolved_ips, "error": val_res.error},
            reputation={},
            status="blocked",
            error_message=val_res.error,
            created_at=now,
        )
        db.add(record)
        db.commit()

        return UrlAnalysisResponse(
            id=analysis_id,
            analysis_type="url",
            input_url=raw_url,
            normalized_url=val_res.normalized_url or raw_url,
            hostname=val_res.hostname or "unknown",
            created_at=now,
            risk_level=risk_level,
            risk_score=risk_score,
            findings=findings,
            redirect_chain=[],
            domain_info={"resolved_ips": val_res.resolved_ips, "blocked": True},
            reputation={},
            recommendations=recs,
            limitations=limits,
            status="blocked",
            error_message=val_res.error,
        )

    # 2. Static URL Structural Analysis
    analyzer = UrlStructureAnalyzer()
    findings, metadata = analyzer.analyze(raw_url, val_res.normalized_url)

    # 3. Controlled Redirect & Network Inspection (if enabled)
    redirect_chain: list[dict[str, Any]] = []
    domain_info: dict[str, Any] = {"resolved_ips": val_res.resolved_ips, "scheme": val_res.scheme}
    is_unreachable = False

    if request.check_network:
        inspector = SafeNetworkInspector()
        redirect_chain, domain_info, net_findings = inspector.inspect_url(val_res.normalized_url)
        findings.extend(net_findings)
        if any(hop.get("status") == "connection_failed" for hop in redirect_chain):
            is_unreachable = True

    metadata["redirect_chain"] = redirect_chain
    metadata["domain_info"] = domain_info

    # 4. Optional External Reputation Lookup (requires explicit consent)
    reputation_data: dict[str, Any] = {}
    if request.check_reputation:
        reputation_data = reputation_provider.lookup_url(val_res.normalized_url)
    else:
        reputation_data = {
            "status": "not_requested",
            "note": "External threat intelligence lookup was not requested by user.",
        }

    # 5. Deterministic Risk Assessment
    risk_level, risk_score, recs, limits = risk_engine.evaluate(
        findings=findings,
        reputation=reputation_data if request.check_reputation else None,
        is_unreachable=is_unreachable,
    )

    # 6. Optional AI Explanation
    ai_explanation: str | None = None
    if request.explain_ai:
        ai_explanation = guardian_explainer.explain(
            target=val_res.normalized_url,
            target_type="URL",
            risk_level=risk_level,
            risk_score=risk_score,
            findings=findings,
            reputation=reputation_data,
        )

    # 7. Persist Analysis Record
    record = GuardianAnalysis(
        id=analysis_id,
        analysis_type="url",
        target=val_res.normalized_url,
        target_identifier=val_res.hostname,
        risk_level=risk_level,
        risk_score=risk_score,
        findings=[f.model_dump() for f in findings],
        target_metadata=metadata,
        reputation=reputation_data,
        ai_explanation=ai_explanation,
        status="completed",
        created_at=now,
    )
    db.add(record)
    db.commit()

    return UrlAnalysisResponse(
        id=analysis_id,
        analysis_type="url",
        input_url=raw_url,
        normalized_url=val_res.normalized_url,
        hostname=val_res.hostname,
        created_at=now,
        risk_level=risk_level,
        risk_score=risk_score,
        findings=findings,
        redirect_chain=redirect_chain,
        domain_info=domain_info,
        reputation=reputation_data,
        recommendations=recs,
        limitations=limits,
        ai_explanation=ai_explanation,
        status="completed",
    )


@router.post(
    "/file",
    response_model=FileAnalysisResponse,
    summary="Defensive File Security Analysis",
    description="Accepts an uploaded file for safe static analysis, or client-computed SHA-256 hash lookup.",
)
async def analyze_file_endpoint(
    request: Request,
    db: Session = Depends(get_db),
) -> FileAnalysisResponse:
    content_type = request.headers.get("content-type", "")
    analysis_id = str(uuid.uuid4())
    now = utc_now()
    analyzer = FileSecurityAnalyzer()

    # Case A: Multipart File Upload
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file: UploadFile | None = form.get("file")  # type: ignore
        check_reputation_str = form.get("check_reputation", "false")
        explain_ai_str = form.get("explain_ai", "false")
        check_reputation = str(check_reputation_str).lower() in {"true", "1", "yes"}
        explain_ai = str(explain_ai_str).lower() in {"true", "1", "yes"}

        if not uploaded_file or not uploaded_file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No file uploaded in multipart form data.",
            )

        try:
            hashes, detected_format, detected_mime, findings, static_features, file_size = (
                analyzer.analyze_file_stream(uploaded_file.file, uploaded_file.filename)
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
        except Exception as exc:
            logger.error("File analysis failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"File inspection failed: {exc}")

        # Optional external hash lookup (only if user consented)
        reputation_data: dict[str, Any] = {}
        if check_reputation:
            reputation_data = reputation_provider.lookup_file_hash(hashes["sha256"])
        else:
            reputation_data = {
                "status": "not_requested",
                "note": "External threat intelligence lookup was not requested by user.",
            }

        risk_level, risk_score, recs, limits = risk_engine.evaluate(
            findings=findings,
            reputation=reputation_data if check_reputation else None,
        )

        ai_explanation: str | None = None
        if explain_ai:
            ai_explanation = guardian_explainer.explain(
                target=uploaded_file.filename,
                target_type="File",
                risk_level=risk_level,
                risk_score=risk_score,
                findings=findings,
                reputation=reputation_data,
            )

        metadata = {
            "hashes": hashes,
            "static_features": static_features,
            "detected_mime": detected_mime,
            "magic_signature": detected_format,
            "file_size_bytes": file_size,
        }

        record = GuardianAnalysis(
            id=analysis_id,
            analysis_type="file",
            target=uploaded_file.filename,
            target_identifier=hashes["sha256"],
            risk_level=risk_level,
            risk_score=risk_score,
            findings=[f.model_dump() for f in findings],
            target_metadata=metadata,
            reputation=reputation_data,
            ai_explanation=ai_explanation,
            status="completed",
            created_at=now,
        )
        db.add(record)
        db.commit()

        return FileAnalysisResponse(
            id=analysis_id,
            analysis_type="file",
            original_filename=uploaded_file.filename,
            file_size_bytes=file_size,
            detected_mime=detected_mime,
            magic_signature=detected_format,
            sha256=hashes["sha256"],
            sha1=hashes["sha1"],
            md5=hashes["md5"],
            created_at=now,
            risk_level=risk_level,
            risk_score=risk_score,
            findings=findings,
            static_features=static_features,
            reputation=reputation_data,
            recommendations=recs,
            limitations=limits,
            ai_explanation=ai_explanation,
            status="completed",
        )

    # Case B: JSON Hash Lookup Request (Client-side pre-hashed)
    try:
        body = await request.json()
        req_obj = FileHashLookupRequest(**body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Expected multipart/form-data with file or valid JSON hash payload: {exc}",
        )

    findings = []
    static_features = {"sha256_client": req_obj.sha256, "file_size_bytes": req_obj.size_bytes}

    # Static filename extension check
    if req_obj.filename:
        from app.guardian.file_analyzer import DANGEROUS_EXTENSIONS
        ext = ("." + req_obj.filename.split(".")[-1]).lower() if "." in req_obj.filename else ""
        if ext in DANGEROUS_EXTENSIONS:
            findings.append(
                GuardianFinding(
                    name="Potentially Dangerous Executable File Extension",
                    description=f"Filename '{req_obj.filename}' ends with an executable or script extension ({ext}).",
                    severity="medium",
                    evidence=f"Filename: {req_obj.filename}",
                    recommendation="Ensure this file came from a verified publisher before executing.",
                )
            )

    reputation_data: dict[str, Any] = {}
    if req_obj.check_reputation and req_obj.sha256:
        reputation_data = reputation_provider.lookup_file_hash(req_obj.sha256)
    else:
        reputation_data = {
            "status": "not_requested",
            "note": "External threat intelligence lookup was not requested by user.",
        }

    risk_level, risk_score, recs, limits = risk_engine.evaluate(
        findings=findings,
        reputation=reputation_data if req_obj.check_reputation else None,
    )

    ai_explanation: str | None = None
    if req_obj.explain_ai:
        ai_explanation = guardian_explainer.explain(
            target=req_obj.filename or req_obj.sha256,
            target_type="File Hash",
            risk_level=risk_level,
            risk_score=risk_score,
            findings=findings,
            reputation=reputation_data,
        )

    metadata = {
        "hashes": {"sha256": req_obj.sha256},
        "static_features": static_features,
        "detected_mime": req_obj.mime_type,
        "magic_signature": "Client SHA-256 Digest",
        "file_size_bytes": req_obj.size_bytes,
    }

    record = GuardianAnalysis(
        id=analysis_id,
        analysis_type="file",
        target=req_obj.filename or req_obj.sha256,
        target_identifier=req_obj.sha256,
        risk_level=risk_level,
        risk_score=risk_score,
        findings=[f.model_dump() for f in findings],
        target_metadata=metadata,
        reputation=reputation_data,
        ai_explanation=ai_explanation,
        status="completed",
        created_at=now,
    )
    db.add(record)
    db.commit()

    return FileAnalysisResponse(
        id=analysis_id,
        analysis_type="file",
        original_filename=req_obj.filename or "unknown_file",
        file_size_bytes=req_obj.size_bytes,
        detected_mime=req_obj.mime_type or "application/octet-stream",
        magic_signature="Client SHA-256 Digest",
        sha256=req_obj.sha256,
        sha1="",
        md5="",
        created_at=now,
        risk_level=risk_level,
        risk_score=risk_score,
        findings=findings,
        static_features=static_features,
        reputation=reputation_data,
        recommendations=recs,
        limitations=limits,
        ai_explanation=ai_explanation,
        status="completed",
    )


@router.get(
    "/analysis/{analysis_id}",
    summary="Get previous security analysis report",
)
def get_analysis_endpoint(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    analysis = db.query(GuardianAnalysis).filter(GuardianAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found.")

    findings_list = [GuardianFinding(**f) for f in (analysis.findings or [])]
    meta = analysis.target_metadata or {}

    if analysis.analysis_type == "url":
        _, _, recs, limits = risk_engine.evaluate(findings_list, analysis.reputation)
        return UrlAnalysisResponse(
            id=analysis.id,
            analysis_type="url",
            input_url=analysis.target,
            normalized_url=analysis.target,
            hostname=analysis.target_identifier or "unknown",
            created_at=analysis.created_at,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            findings=findings_list,
            redirect_chain=meta.get("redirect_chain", []),
            domain_info=meta.get("domain_info", {}),
            reputation=analysis.reputation or {},
            recommendations=recs,
            limitations=limits,
            ai_explanation=analysis.ai_explanation,
            status=analysis.status,
            error_message=analysis.error_message,
        ).model_dump()
    else:
        hashes = meta.get("hashes", {})
        _, _, recs, limits = risk_engine.evaluate(findings_list, analysis.reputation)
        return FileAnalysisResponse(
            id=analysis.id,
            analysis_type="file",
            original_filename=analysis.target,
            file_size_bytes=meta.get("file_size_bytes", 0),
            detected_mime=meta.get("detected_mime", "application/octet-stream"),
            magic_signature=meta.get("magic_signature", "Unknown"),
            sha256=hashes.get("sha256", analysis.target_identifier or ""),
            sha1=hashes.get("sha1", ""),
            md5=hashes.get("md5", ""),
            created_at=analysis.created_at,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            findings=findings_list,
            static_features=meta.get("static_features", {}),
            reputation=analysis.reputation or {},
            recommendations=recs,
            limitations=limits,
            ai_explanation=analysis.ai_explanation,
            status=analysis.status,
            error_message=analysis.error_message,
        ).model_dump()


@router.get(
    "/history",
    response_model=GuardianHistoryListResponse,
    summary="List security analysis history",
)
def list_history_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> GuardianHistoryListResponse:
    query = db.query(GuardianAnalysis).order_by(GuardianAnalysis.created_at.desc())
    total = query.count()
    items = query.offset(offset).limit(limit).all()

    return GuardianHistoryListResponse(
        items=[
            GuardianHistoryItemResponse(
                id=item.id,
                analysis_type=item.analysis_type,
                target=item.target,
                target_identifier=item.target_identifier,
                risk_level=item.risk_level,
                risk_score=item.risk_score,
                findings_count=item.findings_count,
                created_at=item.created_at,
                status=item.status,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/analysis/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single security analysis",
)
def delete_analysis_endpoint(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> None:
    analysis = db.query(GuardianAnalysis).filter(GuardianAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found.")
    db.delete(analysis)
    db.commit()


@router.delete(
    "/history",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all security analysis history",
)
def clear_history_endpoint(
    db: Session = Depends(get_db),
) -> None:
    db.query(GuardianAnalysis).delete()
    db.commit()
