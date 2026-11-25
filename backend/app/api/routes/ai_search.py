"""FastAPI routes for LUMO Grounded AI Search and Research queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.ai.orchestrator import AISearchOrchestrator
from app.ai.router import ai_provider_router
from app.core.logging import get_logger
from app.database.connection import get_db
from app.history.service import record_search
from app.schemas.ai import AISearchRequest, AISearchResponse

logger = get_logger("api.search.ai")

router = APIRouter(prefix="/search/ai", tags=["ai_search"])


@router.post(
    "",
    response_model=AISearchResponse,
    summary="Execute Grounded AI Search / Research",
    description="Retrieves evidence via Hybrid Search, sanitizes context, routes to the configured AI provider, and returns a cited response.",
)
def ai_search_endpoint(
    request: AISearchRequest,
    x_history_disabled: Annotated[bool, Header(alias="X-History-Disabled")] = False,
    db: Session = Depends(get_db),
) -> AISearchResponse:
    orchestrator = AISearchOrchestrator(db=db)
    response = orchestrator.search(request)

    # Persist in search history if non-empty and privacy not requested
    privacy_active = request.privacy or x_history_disabled
    if request.query.strip():
        try:
            filters = {
                "provider": response.provider,
                "model": response.model,
                "fallback_used": response.fallback_used,
            }
            if request.domain:
                filters["domain"] = request.domain
            if request.language:
                filters["language"] = request.language

            record_search(
                db=db,
                query=request.query,
                mode="ai",
                total_results=len(response.citations),
                filters=filters,
                session_id=request.session_id,
                privacy_disabled=privacy_active,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Could not persist AI search history: %s", exc)

    return response


@router.get(
    "/status",
    summary="Get AI Search and Provider status",
    description="Returns availability status for configured AI providers without exposing API keys or secrets.",
)
def ai_status_endpoint() -> dict:
    return {
        "status": "ready",
        "router": ai_provider_router.get_status(),
    }
