"""Liveness and readiness endpoints.

Responses stay limited to application status. They do not include hosts,
usernames, database URLs, or exception text.
"""

from typing import Any, Literal
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.ai.router import ai_provider_router
from app.config import Settings
from app.core.observability import observability_registry
from app.database.connection import check_database_connection, get_engine, get_session_factory
from app.ops.migrations import CURRENT_SCHEMA_VERSION, get_migration_status

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    application: str
    version: str


class ReadinessChecks(BaseModel):
    database: Literal["connected", "unavailable"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    application: str
    checks: ReadinessChecks = Field(description="Dependency checks without internal details.")


class DetailedReadinessResponse(ReadinessResponse):
    uptime_seconds: float = 0.0
    db_latency_ms: float | None = None


def health_payload(settings: Settings) -> HealthResponse:
    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
    )


def readiness_payload(settings: Settings) -> ReadinessResponse:
    database_ok = check_database_connection()
    return ReadinessResponse(
        status="ready" if database_ok else "not_ready",
        application=settings.app_name,
        checks=ReadinessChecks(database="connected" if database_ok else "unavailable"),
    )


def detailed_readiness_payload(settings: Settings) -> DetailedReadinessResponse:
    t0 = time.perf_counter()
    database_ok = check_database_connection()
    db_ms = round((time.perf_counter() - t0) * 1000, 2)
    return DetailedReadinessResponse(
        status="ready" if database_ok else "not_ready",
        application=settings.app_name,
        uptime_seconds=observability_registry.uptime_seconds(),
        db_latency_ms=db_ms if database_ok else None,
        checks=ReadinessChecks(database="connected" if database_ok else "unavailable"),
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness")
def health(request: Request) -> HealthResponse:
    """Report that the API process is running. This does not check PostgreSQL."""
    return health_payload(request.app.state.settings)


@router.get("/health/live", response_model=HealthResponse, summary="Liveness Probe")
def health_live(request: Request) -> HealthResponse:
    """Kubernetes/load-balancer liveness probe."""
    return health_payload(request.app.state.settings)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness",
    responses={503: {"model": ReadinessResponse}},
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Report whether the database accepted a connection."""
    payload = readiness_payload(request.app.state.settings)
    if payload.status != "ready":
        response.status_code = 503
    return payload


@router.get(
    "/health/ready",
    response_model=DetailedReadinessResponse,
    summary="Readiness Probe",
    responses={503: {"model": DetailedReadinessResponse}},
)
def health_ready(request: Request, response: Response) -> DetailedReadinessResponse:
    """Standardized readiness probe with DB latency and uptime."""
    payload = detailed_readiness_payload(request.app.state.settings)
    if payload.status != "ready":
        response.status_code = 503
    return payload


class DiagnosticsResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    application: str
    version: str
    environment: str
    uptime_seconds: float = 0.0
    schema_version: int = 0
    database: dict[str, Any]
    search_index: dict[str, int]
    knowledge_graph: dict[str, int]
    ai_providers: dict[str, Any]
    vector_store: dict[str, Any]
    guardian: dict[str, Any]
    workspace: dict[str, int] = Field(default_factory=dict)
    crawler: dict[str, int] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    background_jobs: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/health/diagnostics",
    response_model=DiagnosticsResponse,
    summary="Platform Diagnostics",
    description="Inspect platform health across database, search index, knowledge graph, AI providers, and Guardian without exposing credentials.",
)
def diagnostics(request: Request) -> DiagnosticsResponse:
    settings: Settings = request.app.state.settings
    t_db = time.perf_counter()
    db_ok = check_database_connection()
    db_latency_ms = round((time.perf_counter() - t_db) * 1000, 2) if db_ok else None
    engine = get_engine()
    dialect = engine.dialect.name if engine is not None else "unknown"
    mig = get_migration_status() if db_ok else {"current_version": 0}

    total_docs = 0
    semantic_docs = 0
    total_entities = 0
    total_rels = 0
    total_guardian = 0
    total_ws_items = 0
    total_ws_notes = 0
    total_crawl_sessions = 0
    active_crawl_sessions = 0
    active_eval_runs = 0
    failed_eval_runs = 0
    active_research_sessions = 0
    failed_research_sessions = 0

    if db_ok:
        factory = get_session_factory()
        if factory is not None:
            try:
                from app.models.crawler import CrawlSession
                from app.models.document import Document
                from app.models.evaluation import EvaluationRun
                from app.models.graph import Entity, Relationship
                from app.models.guardian import GuardianAnalysis
                from app.models.research import ResearchSession
                from app.models.workspace import WorkspaceItem, WorkspaceNote

                with factory() as db:
                    total_docs = db.query(func.count(Document.id)).scalar() or 0
                    semantic_docs = (
                        db.query(func.count(Document.id))
                        .filter(Document.semantic_status == "indexed")
                        .scalar()
                        or 0
                    )
                    total_entities = db.query(func.count(Entity.id)).scalar() or 0
                    total_rels = db.query(func.count(Relationship.id)).scalar() or 0
                    total_guardian = db.query(func.count(GuardianAnalysis.id)).scalar() or 0
                    total_ws_items = db.query(func.count(WorkspaceItem.id)).scalar() or 0
                    total_ws_notes = db.query(func.count(WorkspaceNote.id)).scalar() or 0
                    total_crawl_sessions = db.query(func.count(CrawlSession.id)).scalar() or 0
                    active_crawl_sessions = (
                        db.query(func.count(CrawlSession.id))
                        .filter(CrawlSession.status == "running")
                        .scalar()
                        or 0
                    )
                    active_eval_runs = (
                        db.query(func.count(EvaluationRun.id))
                        .filter(EvaluationRun.status == "running")
                        .scalar()
                        or 0
                    )
                    failed_eval_runs = (
                        db.query(func.count(EvaluationRun.id))
                        .filter(EvaluationRun.status == "failed")
                        .scalar()
                        or 0
                    )
                    active_research_sessions = (
                        db.query(func.count(ResearchSession.id))
                        .filter(ResearchSession.status == "running")
                        .scalar()
                        or 0
                    )
                    failed_research_sessions = (
                        db.query(func.count(ResearchSession.id))
                        .filter(ResearchSession.status == "failed")
                        .scalar()
                        or 0
                    )
            except Exception:
                pass

    # Check AI provider configuration status without leaking secrets
    ollama_reachable = False
    if settings.ollama_enabled:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=1.5) as resp:
                ollama_reachable = resp.status == 200
        except Exception:
            ollama_reachable = False

    provider_status = ai_provider_router.get_status()
    return DiagnosticsResponse(
        status="healthy" if db_ok else "degraded",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=observability_registry.uptime_seconds(),
        schema_version=int(mig.get("current_version", 0) or 0),
        database={
            "status": "connected" if db_ok else "unavailable",
            "dialect": dialect,
            "latency_ms": db_latency_ms,
        },
        search_index={
            "total_documents": total_docs,
            "semantic_indexed_documents": semantic_docs,
        },
        knowledge_graph={
            "total_entities": total_entities,
            "total_relationships": total_rels,
        },
        ai_providers={
            "primary": settings.ai_primary_provider,
            "fallback": settings.ai_fallback_provider or None,
            "gemini_configured": bool(settings.gemini_api_key.strip()),
            "grok_configured": bool(settings.grok_api_key.strip()),
            "ollama_enabled": settings.ollama_enabled,
            "ollama_reachable": ollama_reachable,
            "circuit_breakers": provider_status.get("providers", {}),
        },
        vector_store={
            "qdrant_configured": bool(settings.qdrant_url or settings.qdrant_storage_path),
            "collection_name": settings.qdrant_collection_name,
        },
        guardian={
            "virustotal_configured": bool(settings.guardian_virustotal_api_key.strip()),
            "total_analyses": total_guardian,
        },
        workspace={
            "total_items": total_ws_items,
            "total_notes": total_ws_notes,
        },
        crawler={
            "total_sessions": total_crawl_sessions,
            "active_sessions": active_crawl_sessions,
        },
        storage={
            "mode": "desktop" if __import__("os").environ.get("LUMO_DATA_DIR") else "local",
            "database_dialect": dialect,
            "vector_storage_configured": bool(settings.qdrant_storage_path),
        },
        background_jobs={
            "active_total": active_crawl_sessions + active_eval_runs + active_research_sessions,
            "failed_total": failed_eval_runs + failed_research_sessions,
            "crawler_active": active_crawl_sessions,
            "evaluation_active": active_eval_runs,
            "evaluation_failed": failed_eval_runs,
            "research_active": active_research_sessions,
            "research_failed": failed_research_sessions,
        },
        observability=observability_registry.snapshot(),
    )


@router.get("/system/info", summary="Protected System Information")
def system_info(request: Request) -> dict[str, Any]:
    """Return non-sensitive system version, migration version, enabled modules, and health summary."""
    cfg: Settings = request.app.state.settings
    db_ok = check_database_connection()
    mig = get_migration_status() if db_ok else {"current_version": 0, "target_version": CURRENT_SCHEMA_VERSION}
    return {
        "application": cfg.app_name,
        "version": cfg.app_version,
        "api_version": "v1",
        "phase": "26",
        "environment": cfg.environment,
        "health": "healthy" if db_ok else "degraded",
        "uptime_seconds": observability_registry.uptime_seconds(),
        "database_migration_version": mig.get("current_version", 0),
        "target_migration_version": CURRENT_SCHEMA_VERSION,
        "enabled_modules": [
            "classic_search",
            "semantic_search",
            "hybrid_search",
            "ai_search",
            "research_agent",
            "download_guardian",
            "knowledge_graph",
            "personal_workspace",
            "universal_data_intelligence",
            "evaluation_engine",
            "system_observability",
        ],
        "capabilities": {
            "local_only_ai": cfg.local_only_ai,
            "ollama_enabled": cfg.ollama_enabled,
            "rate_limit_per_minute": cfg.rate_limit_per_minute,
        },
    }
