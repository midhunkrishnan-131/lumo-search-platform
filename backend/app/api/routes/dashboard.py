"""FastAPI aggregation routes for LUMO Phase 19: Intelligence Command Center."""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.router import AIProviderRouter
from app.api.routes.health import diagnostics as health_diagnostics
from app.core.logging import get_logger
from app.database.connection import get_db
from app.intelligence.security import redact_secrets
from app.models.automation import Automation, AutomationExecution, AutomationNotification
from app.models.document import Document
from app.models.graph import Entity, Relationship
from app.models.guardian import GuardianAnalysis
from app.models.history import SearchHistory
from app.models.intelligence import (
    UniversalAnalysisReport,
    UniversalDataset,
    UniversalImportJob,
)
from app.models.personalization import PersonalizationSettings, TopicProfile
from app.models.research import ResearchSession
from app.models.workspace import WorkspaceCollection, WorkspaceItem, WorkspaceNote

logger = get_logger("api.dashboard")

router = APIRouter(prefix="/dashboard", tags=["command-center"])

_HEALTH_CACHE_LOCK = threading.Lock()
_HEALTH_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}
_HEALTH_CACHE_TTL_SECONDS = 10.0


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _safe_count(db: Session, query_fn, degraded: list[str], section: str) -> int:
    try:
        return int(query_fn(db) or 0)
    except Exception as exc:
        logger.warning("Dashboard count failed for %s (%s)", section, type(exc).__name__)
        if section not in degraded:
            degraded.append(section)
        return 0


@router.get("/overview")
def get_dashboard_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Aggregate real platform metrics across all LUMO modules with graceful partial failure."""
    degraded: list[str] = []

    web_docs = _safe_count(
        db,
        lambda s: s.query(func.count(Document.id)).filter(Document.is_duplicate == False).scalar(),  # noqa: E712
        degraded,
        "search_index",
    )
    ws_items = _safe_count(db, lambda s: s.query(func.count(WorkspaceItem.id)).scalar(), degraded, "workspace")
    ws_notes = _safe_count(db, lambda s: s.query(func.count(WorkspaceNote.id)).scalar(), degraded, "workspace")
    ws_collections = _safe_count(db, lambda s: s.query(func.count(WorkspaceCollection.id)).scalar(), degraded, "workspace")
    research_total = _safe_count(db, lambda s: s.query(func.count(ResearchSession.id)).scalar(), degraded, "research")
    research_completed = _safe_count(
        db,
        lambda s: s.query(func.count(ResearchSession.id)).filter(ResearchSession.status == "completed").scalar(),
        degraded,
        "research",
    )
    kg_entities = _safe_count(db, lambda s: s.query(func.count(Entity.id)).scalar(), degraded, "knowledge_graph")
    kg_relationships = _safe_count(db, lambda s: s.query(func.count(Relationship.id)).scalar(), degraded, "knowledge_graph")
    active_automations = _safe_count(
        db,
        lambda s: s.query(func.count(Automation.id)).filter(Automation.enabled == True).scalar(),  # noqa: E712
        degraded,
        "automations",
    )
    pending_imports = _safe_count(
        db,
        lambda s: s.query(func.count(UniversalImportJob.id))
        .filter(UniversalImportJob.status.in_(["pending", "validating", "extracting", "classifying", "indexing"]))
        .scalar(),
        degraded,
        "universal_intelligence",
    )
    failed_imports = _safe_count(
        db,
        lambda s: s.query(func.count(UniversalImportJob.id)).filter(UniversalImportJob.status == "failed").scalar(),
        degraded,
        "universal_intelligence",
    )
    datasets_count = _safe_count(db, lambda s: s.query(func.count(UniversalDataset.id)).scalar(), degraded, "universal_intelligence")
    reports_count = _safe_count(db, lambda s: s.query(func.count(UniversalAnalysisReport.id)).scalar(), degraded, "universal_intelligence")
    guardian_count = _safe_count(db, lambda s: s.query(func.count(GuardianAnalysis.id)).scalar(), degraded, "guardian")
    unread_notifications = _safe_count(
        db,
        lambda s: s.query(func.count(AutomationNotification.id)).filter(AutomationNotification.is_read == False).scalar(),  # noqa: E712
        degraded,
        "notifications",
    )

    return {
        "metrics": {
            "indexed_web_documents": web_docs,
            "personal_documents": ws_items,
            "workspace_notes": ws_notes,
            "workspace_collections": ws_collections,
            "research_sessions": research_total,
            "research_reports": research_completed,
            "knowledge_graph_entities": kg_entities,
            "knowledge_graph_relationships": kg_relationships,
            "active_automations": active_automations,
            "pending_processing_jobs": pending_imports,
            "failed_processing_jobs": failed_imports,
            "datasets": datasets_count,
            "ai_reports": reports_count,
            "guardian_analyses": guardian_count,
            "unread_notifications": unread_notifications,
        },
        "degraded_sections": degraded,
        "generated_at": _iso(datetime.now(timezone.utc)),
    }


@router.get("/activity")
def get_unified_activity(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str = Query(default="all"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Chronological unified activity feed across searches, research, imports, reports, automations, and guardian."""
    events: list[dict[str, Any]] = []
    degraded: list[str] = []
    per_source = max(limit + offset, 20)

    def add_event(
        ev_id: str,
        cat: str,
        title: str,
        detail: str,
        status: str,
        ts: datetime | None,
        href: str,
    ) -> None:
        events.append(
            {
                "id": ev_id,
                "category": cat,
                "title": title,
                "detail": detail,
                "status": status,
                "timestamp": _iso(ts),
                "href": href,
                "_sort": ts.timestamp() if ts else 0.0,
            }
        )

    if category in ("all", "search"):
        try:
            for s in db.query(SearchHistory).order_by(SearchHistory.created_at.desc()).limit(per_source).all():
                add_event(
                    f"search:{s.id}",
                    "search",
                    f"Search: {s.query[:80]}",
                    f"Mode: {s.mode} · {s.total_results} results",
                    "completed",
                    s.created_at,
                    f"./results.html?q={s.query}",
                )
        except Exception:
            degraded.append("search")

    if category in ("all", "research"):
        try:
            for r in db.query(ResearchSession).order_by(ResearchSession.created_at.desc()).limit(per_source).all():
                add_event(
                    f"research:{r.id}",
                    "research",
                    f"Research: {r.topic[:80]}",
                    f"Provider: {r.provider} · Iteration {r.current_iteration}/{r.max_iterations}",
                    r.status,
                    r.completed_at or r.created_at,
                    "./research.html",
                )
        except Exception:
            degraded.append("research")

    if category in ("all", "intelligence"):
        try:
            for j in db.query(UniversalImportJob).order_by(UniversalImportJob.created_at.desc()).limit(per_source).all():
                add_event(
                    f"import:{j.id}",
                    "intelligence",
                    f"Import: {j.file_name or j.source_url or j.id}",
                    f"{j.format_type} · {j.content_category}",
                    j.status,
                    j.completed_at or j.created_at,
                    "./intelligence.html",
                )
            for rep in db.query(UniversalAnalysisReport).order_by(UniversalAnalysisReport.created_at.desc()).limit(per_source).all():
                add_event(
                    f"report:{rep.id}",
                    "intelligence",
                    rep.title[:90],
                    f"{rep.report_type} · {rep.provider or 'deterministic'}",
                    "completed",
                    rep.created_at,
                    "./intelligence.html",
                )
        except Exception:
            degraded.append("intelligence")

    if category in ("all", "automation"):
        try:
            for ex in db.query(AutomationExecution).order_by(AutomationExecution.created_at.desc()).limit(per_source).all():
                add_event(
                    f"exec:{ex.id}",
                    "automation",
                    f"Automation Run ({ex.trigger_source})",
                    ex.output_summary[:120] if ex.output_summary else (ex.error_message or f"Step {ex.current_step_index}/{ex.total_steps}"),
                    ex.status,
                    ex.completed_at or ex.created_at,
                    "./automation.html",
                )
        except Exception:
            degraded.append("automation")

    if category in ("all", "guardian"):
        try:
            for g in db.query(GuardianAnalysis).order_by(GuardianAnalysis.created_at.desc()).limit(per_source).all():
                add_event(
                    f"guardian:{g.id}",
                    "guardian",
                    f"Guardian ({g.analysis_type.upper()}): {g.target[:75]}",
                    f"Risk: {g.risk_level} (score {g.risk_score})",
                    g.status,
                    g.created_at,
                    "./guardian.html",
                )
        except Exception:
            degraded.append("guardian")

    events.sort(key=lambda x: x["_sort"], reverse=True)
    total = len(events)
    sliced = events[offset : offset + limit]
    for item in sliced:
        item.pop("_sort", None)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "category": category,
        "items": sliced,
        "degraded_sections": degraded,
    }


@router.get("/research")
def get_research_overview(limit: int = Query(default=8, ge=1, le=50), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(ResearchSession).order_by(ResearchSession.created_at.desc()).limit(limit).all()
    counts = {
        "total": db.query(func.count(ResearchSession.id)).scalar() or 0,
        "active": db.query(func.count(ResearchSession.id))
        .filter(ResearchSession.status.in_(["pending", "planning", "researching", "analyzing", "generating_report"]))
        .scalar()
        or 0,
        "completed": db.query(func.count(ResearchSession.id)).filter(ResearchSession.status == "completed").scalar() or 0,
        "failed": db.query(func.count(ResearchSession.id)).filter(ResearchSession.status == "failed").scalar() or 0,
    }
    return {
        "counts": counts,
        "recent": [
            {
                "id": r.id,
                "topic": r.topic,
                "status": r.status,
                "provider": r.provider,
                "current_iteration": r.current_iteration,
                "max_iterations": r.max_iterations,
                "created_at": _iso(r.created_at),
                "completed_at": _iso(r.completed_at),
            }
            for r in rows
        ],
    }


@router.get("/automations")
def get_automations_overview(limit: int = Query(default=8, ge=1, le=50), db: Session = Depends(get_db)) -> dict[str, Any]:
    autos = db.query(Automation).order_by(Automation.updated_at.desc()).limit(limit).all()
    execs = db.query(AutomationExecution).order_by(AutomationExecution.created_at.desc()).limit(limit).all()
    return {
        "counts": {
            "total": db.query(func.count(Automation.id)).scalar() or 0,
            "active": db.query(func.count(Automation.id)).filter(Automation.enabled == True).scalar() or 0,  # noqa: E712
            "paused": db.query(func.count(Automation.id)).filter(Automation.enabled == False).scalar() or 0,  # noqa: E712
            "failed_executions": db.query(func.count(AutomationExecution.id))
            .filter(AutomationExecution.status == "failed")
            .scalar()
            or 0,
        },
        "automations": [
            {
                "id": a.id,
                "name": a.name,
                "workflow_type": a.workflow_type,
                "trigger_type": a.trigger_type,
                "enabled": a.enabled,
                "last_run_at": _iso(a.last_run_at),
                "next_run_at": _iso(a.next_run_at),
            }
            for a in autos
        ],
        "recent_executions": [
            {
                "id": e.id,
                "automation_id": e.automation_id,
                "status": e.status,
                "trigger_source": e.trigger_source,
                "output_summary": e.output_summary,
                "error_message": e.error_message,
                "created_at": _iso(e.created_at),
            }
            for e in execs
        ],
    }


@router.get("/ai-status")
def get_ai_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return safe AI provider status and recent AI tasks without exposing API keys."""
    provider_status = AIProviderRouter().get_status()
    recent_reports = (
        db.query(UniversalAnalysisReport)
        .order_by(UniversalAnalysisReport.created_at.desc())
        .limit(6)
        .all()
    )
    return {
        "router": provider_status,
        "recent_tasks": [
            {
                "id": r.id,
                "title": r.title,
                "report_type": r.report_type,
                "provider": r.provider,
                "created_at": _iso(r.created_at),
            }
            for r in recent_reports
        ],
    }


@router.get("/knowledge")
def get_knowledge_overview(limit: int = Query(default=6, ge=1, le=30), db: Session = Depends(get_db)) -> dict[str, Any]:
    items = db.query(WorkspaceItem).order_by(WorkspaceItem.created_at.desc()).limit(limit).all()
    collections = db.query(WorkspaceCollection).order_by(WorkspaceCollection.updated_at.desc()).limit(limit).all()
    notes = db.query(WorkspaceNote).order_by(WorkspaceNote.updated_at.desc()).limit(limit).all()
    topics = db.query(TopicProfile).order_by(TopicProfile.frequency.desc()).limit(8).all()
    pers_settings = db.query(PersonalizationSettings).filter(PersonalizationSettings.id == "default").first()

    return {
        "graph": {
            "entities": db.query(func.count(Entity.id)).scalar() or 0,
            "relationships": db.query(func.count(Relationship.id)).scalar() or 0,
        },
        "personalization_enabled": bool(pers_settings.enabled) if pers_settings else False,
        "recent_items": [
            {"id": i.id, "title": i.title, "source_type": i.source_type, "created_at": _iso(i.created_at)}
            for i in items
        ],
        "collections": [{"id": c.id, "name": c.name} for c in collections],
        "recent_notes": [{"id": n.id, "title": n.title, "updated_at": _iso(n.updated_at)} for n in notes],
        "top_topics": [{"topic": t.topic, "frequency": t.frequency} for t in topics],
    }


@router.get("/guardian")
def get_guardian_overview(limit: int = Query(default=6, ge=1, le=30), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(GuardianAnalysis).order_by(GuardianAnalysis.created_at.desc()).limit(limit).all()
    high_risk = (
        db.query(func.count(GuardianAnalysis.id))
        .filter(GuardianAnalysis.risk_level.in_(["High", "Critical"]))
        .scalar()
        or 0
    )
    return {
        "total": db.query(func.count(GuardianAnalysis.id)).scalar() or 0,
        "high_risk_warnings": high_risk,
        "disclaimer": "Security risk levels reflect static and structural indicators, not definitive safety verdicts.",
        "recent": [
            {
                "id": g.id,
                "analysis_type": g.analysis_type,
                "target": g.target,
                "risk_level": g.risk_level,
                "risk_score": g.risk_score,
                "status": g.status,
                "created_at": _iso(g.created_at),
            }
            for g in rows
        ],
    }


@router.get("/system-health")
def get_system_health(request: Request, force: bool = Query(default=False)) -> dict[str, Any]:
    """Return cached platform diagnostics without exposing credentials or running destructive checks."""
    now = time.monotonic()
    with _HEALTH_CACHE_LOCK:
        if not force and _HEALTH_CACHE["payload"] is not None and now < _HEALTH_CACHE["expires_at"]:
            return _HEALTH_CACHE["payload"]

    try:
        diag = health_diagnostics(request)
        payload = {
            "status": diag.status,
            "application": diag.application,
            "version": diag.version,
            "environment": diag.environment,
            "database": diag.database,
            "search_index": diag.search_index,
            "knowledge_graph": diag.knowledge_graph,
            "ai_providers": diag.ai_providers,
            "vector_store": diag.vector_store,
            "guardian": diag.guardian,
            "workspace": diag.workspace,
            "checked_at": _iso(datetime.now(timezone.utc)),
        }
    except Exception as exc:
        payload = {
            "status": "degraded",
            "error": redact_secrets(str(exc)),
            "checked_at": _iso(datetime.now(timezone.utc)),
        }

    with _HEALTH_CACHE_LOCK:
        _HEALTH_CACHE["payload"] = payload
        _HEALTH_CACHE["expires_at"] = now + _HEALTH_CACHE_TTL_SECONDS

    return payload


@router.get("/notifications")
def get_dashboard_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate notifications from existing AutomationNotification storage."""
    q = db.query(AutomationNotification)
    if unread_only:
        q = q.filter(AutomationNotification.is_read == False)  # noqa: E712
    rows = q.order_by(AutomationNotification.created_at.desc()).limit(limit).all()
    unread_count = (
        db.query(func.count(AutomationNotification.id))
        .filter(AutomationNotification.is_read == False)  # noqa: E712
        .scalar()
        or 0
    )
    return {
        "unread_count": unread_count,
        "items": [
            {
                "id": n.id,
                "automation_id": n.automation_id,
                "execution_id": n.execution_id,
                "event_type": n.event_type,
                "title": n.title,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": _iso(n.created_at),
            }
            for n in rows
        ],
    }


@router.get("/integrity")
def get_data_integrity_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only diagnostic check for cross-module data synchronization inconsistencies."""
    from app.models.graph import EntityDocument

    interrupted_jobs = (
        db.query(func.count(UniversalImportJob.id))
        .filter(UniversalImportJob.status.in_(["pending", "validating", "extracting", "classifying", "indexing"]))
        .scalar()
        or 0
    )
    orphaned_datasets = (
        db.query(func.count(UniversalDataset.id))
        .filter(UniversalDataset.workspace_item_id.is_(None))
        .scalar()
        or 0
    )
    total_entity_links = db.query(func.count(EntityDocument.id)).scalar() or 0
    healthy = interrupted_jobs == 0 and orphaned_datasets == 0
    return {
        "status": "consistent" if healthy else "attention_needed",
        "checks": {
            "interrupted_import_jobs": interrupted_jobs,
            "orphaned_datasets": orphaned_datasets,
            "entity_document_links": total_entity_links,
        },
        "checked_at": _iso(datetime.now(timezone.utc)),
    }
