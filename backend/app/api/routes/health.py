"""Liveness and readiness endpoints.

Responses stay limited to application status. They do not include hosts,
usernames, database URLs, or exception text.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.config import Settings
from app.database.connection import check_database_connection, get_engine, get_session_factory

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


@router.get("/health", response_model=HealthResponse, summary="Liveness")
def health(request: Request) -> HealthResponse:
    """Report that the API process is running. This does not check PostgreSQL."""
    return health_payload(request.app.state.settings)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness",
    responses={503: {"model": ReadinessResponse}},
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Report whether PostgreSQL accepted a connection."""
    payload = readiness_payload(request.app.state.settings)
    if payload.status != "ready":
        response.status_code = 503
    return payload


class DiagnosticsResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    application: str
    version: str
    environment: str
    database: dict[str, Any]
    search_index: dict[str, int]
    knowledge_graph: dict[str, int]
    ai_providers: dict[str, Any]
    vector_store: dict[str, Any]
    guardian: dict[str, Any]
    workspace: dict[str, int] = Field(default_factory=dict)
    crawler: dict[str, int] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/health/diagnostics",
    response_model=DiagnosticsResponse,
    summary="Platform Diagnostics",
    description="Inspect platform health across database, search index, knowledge graph, AI providers, and Guardian without exposing credentials.",
)
def diagnostics(request: Request) -> DiagnosticsResponse:
    settings: Settings = request.app.state.settings
    db_ok = check_database_connection()
    engine = get_engine()
    dialect = engine.dialect.name if engine is not None else "unknown"

    total_docs = 0
    semantic_docs = 0
    total_entities = 0
    total_rels = 0
    total_guardian = 0
    total_ws_items = 0
    total_ws_notes = 0
    total_crawl_sessions = 0
    active_crawl_sessions = 0

    if db_ok:
        factory = get_session_factory()
        if factory is not None:
            try:
                from app.models.crawler import CrawlSession
                from app.models.document import Document
                from app.models.graph import Entity, Relationship
                from app.models.guardian import GuardianAnalysis
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

    return DiagnosticsResponse(
        status="healthy" if db_ok else "degraded",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database={
            "status": "connected" if db_ok else "unavailable",
            "dialect": dialect,
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
    )
