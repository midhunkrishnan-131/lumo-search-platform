"""FastAPI endpoint for Classic Search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import get_db, get_session_factory
from app.history.service import record_search
from app.schemas.search import SearchResponse, SearchResultItem
from app.search.engine import ClassicSearchEngine, SearchResult, SearchResultSet
from app.search.hybrid import HybridSearchOrchestrator
from app.search.web_provider import fetch_and_extract_webpage, live_web_provider
from app.semantic.search import SemanticSearchEngine
from app.ai.orchestrator import AISearchOrchestrator
from app.schemas.ai import AISearchRequest

logger = get_logger("api.search")

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Classic Search over indexed documents",
    description="Performs keyword and full-text retrieval across indexed document titles, descriptions, and main content.",
)
def search_endpoint(
    q: Annotated[str, Query(max_length=400, description="Search query string")] = "",
    mode: Annotated[str, Query(description="Search mode: classic, semantic, or hybrid")] = "classic",
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page")] = 8,
    sort: Annotated[str, Query(description="Sort order: relevance, newest, title")] = "relevance",
    category: Annotated[str | None, Query(description="Category filter")] = None,
    domain: Annotated[str | None, Query(description="Domain filter")] = None,
    language: Annotated[str | None, Query(description="Language filter")] = None,
    session_id: Annotated[str | None, Query(description="Optional client session ID")] = None,
    privacy: Annotated[bool, Query(description="When True, prevents search history logging")] = False,
    x_history_disabled: Annotated[bool, Header(alias="X-History-Disabled")] = False,
    db: Session = Depends(get_db),
) -> SearchResponse:
    degraded = False
    metadata: dict[str, str | int | float | bool] = {}

    if mode == "web":
        web_hits = live_web_provider.search(query=q, page=page, per_page=per_page)
        sr_items = [
            SearchResult(
                id=h.id,
                url=h.url,
                title=h.title,
                description=h.snippet,
                domain=h.domain,
                snippet=h.snippet,
                score=h.score,
                published_at=h.published_at,
                sources=[h.source_provider],
            )
            for h in web_hits
        ]
        search_set = SearchResultSet(
            query=q,
            mode="web",
            total=len(sr_items),
            page=page,
            per_page=per_page,
            total_pages=1,
            results=sr_items,
        )
        metadata["web_provider"] = live_web_provider.name
    elif mode == "semantic":
        semantic_engine = SemanticSearchEngine(db)
        search_set = semantic_engine.search(
            query=q,
            page=page,
            per_page=per_page,
            domain=domain,
            language=language,
        )
    elif mode == "hybrid":
        orchestrator = HybridSearchOrchestrator(db)
        search_set, degraded, metadata = orchestrator.search(
            query=q,
            page=page,
            per_page=per_page,
            domain=domain,
            language=language,
        )
    elif mode == "ai":
        orchestrator = HybridSearchOrchestrator(db)
        search_set, degraded, metadata = orchestrator.search(
            query=q,
            page=page,
            per_page=per_page,
            domain=domain,
            language=language,
        )
        ai_orch = AISearchOrchestrator(db)
        ai_resp = ai_orch.search(AISearchRequest(query=q, page_size=per_page, domain=domain, language=language))
        metadata["ai_answer"] = ai_resp.answer
        metadata["ai_provider"] = ai_resp.provider
        metadata["ai_status"] = ai_resp.status
    else:
        classic_engine = ClassicSearchEngine(db)
        search_set = classic_engine.search(
            query=q,
            page=page,
            per_page=per_page,
            sort=sort,
            domain=domain,
            language=language,
        )

    # Automatically record search history and apply opt-in personalization if enabled
    privacy_active = privacy or x_history_disabled
    results_list = search_set.results
    try:
        from app.personalization.service import PersonalizationService
        p_service = PersonalizationService(db)
        if not privacy_active:
            results_list, _, personalized_applied = p_service.rerank_search_results(results_list)
            metadata["personalized"] = personalized_applied
        if q.strip():
            p_service.record_search_signal(q, privacy_disabled=privacy_active)
    except Exception as exc:
        logger.debug("Personalization hook skipped: %s", exc)

    if q.strip():
        try:
            filters = {}
            if domain:
                filters["domain"] = domain
            if language:
                filters["language"] = language
            if category and category != "All":
                filters["category"] = category

            record_search(
                db=db,
                query=q,
                mode=mode,
                total_results=search_set.total,
                filters=filters,
                session_id=session_id,
                privacy_disabled=privacy_active,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Could not persist search history: %s", exc)

    return SearchResponse(
        source="api",
        query=search_set.query,
        mode=search_set.mode,
        total=search_set.total,
        page=search_set.page,
        per_page=search_set.per_page,
        total_pages=search_set.total_pages,
        results=[SearchResultItem.model_validate(r) for r in results_list],
        degraded=degraded,
        execution_metadata=metadata,
    )


@router.get(
    "/hybrid",
    response_model=SearchResponse,
    summary="Hybrid Search (Classic + Semantic with RRF)",
    description="Fuses PostgreSQL full-text keyword retrieval and Qdrant semantic vector similarity using Reciprocal Rank Fusion.",
)
def hybrid_search_endpoint(
    q: Annotated[str, Query(max_length=400, description="Search query string")] = "",
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page")] = 8,
    category: Annotated[str | None, Query(description="Category filter")] = None,
    domain: Annotated[str | None, Query(description="Domain filter")] = None,
    language: Annotated[str | None, Query(description="Language filter")] = None,
    k: Annotated[int | None, Query(ge=1, le=500, description="RRF smoothing constant k")] = None,
    session_id: Annotated[str | None, Query(description="Optional client session ID")] = None,
    privacy: Annotated[bool, Query(description="When True, prevents search history logging")] = False,
    x_history_disabled: Annotated[bool, Header(alias="X-History-Disabled")] = False,
    db: Session = Depends(get_db),
) -> SearchResponse:
    orchestrator = HybridSearchOrchestrator(db)
    search_set, degraded, metadata = orchestrator.search(
        query=q,
        page=page,
        per_page=per_page,
        domain=domain,
        language=language,
        k=k,
    )

    # Automatically record search history if query is non-empty and privacy not requested
    privacy_active = privacy or x_history_disabled
    if q.strip():
        try:
            filters = {}
            if domain:
                filters["domain"] = domain
            if language:
                filters["language"] = language
            if category and category != "All":
                filters["category"] = category

            record_search(
                db=db,
                query=q,
                mode="hybrid",
                total_results=search_set.total,
                filters=filters,
                session_id=session_id,
                privacy_disabled=privacy_active,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Could not persist hybrid search history: %s", exc)

    return SearchResponse(
        source="api",
        query=search_set.query,
        mode="hybrid",
        total=search_set.total,
        page=search_set.page,
        per_page=search_set.per_page,
        total_pages=search_set.total_pages,
        results=[SearchResultItem.model_validate(r) for r in search_set.results],
        degraded=degraded,
        execution_metadata=metadata,
    )


class WebExtractRequest(BaseModel):
    url: str


@router.get("/web", response_model=SearchResponse, summary="Live Public Internet Search")
def web_search_endpoint(
    q: Annotated[str, Query(min_length=1, max_length=400)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=20)] = 8,
) -> SearchResponse:
    try:
        web_hits = live_web_provider.search(query=q, page=page, per_page=per_page)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    sr_items = [
        SearchResult(
            id=h.id,
            url=h.url,
            title=h.title,
            description=h.snippet,
            domain=h.domain,
            snippet=h.snippet,
            score=h.score,
            published_at=h.published_at,
            sources=[h.source_provider],
        )
        for h in web_hits
    ]
    return SearchResponse(
        source="api",
        query=q,
        mode="web",
        total=len(sr_items),
        page=page,
        per_page=per_page,
        total_pages=1,
        results=[SearchResultItem.model_validate(r) for r in sr_items],
        degraded=False,
        execution_metadata={"web_provider": live_web_provider.name},
    )


@router.post("/extract", summary="SSRF-Safe Webpage Content Extraction")
def extract_webpage_endpoint(payload: WebExtractRequest):
    try:
        return fetch_and_extract_webpage(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
