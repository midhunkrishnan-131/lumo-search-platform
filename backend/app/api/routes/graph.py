"""FastAPI routes for LUMO Phase 11: Knowledge Graph & Entity Intelligence."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai.router import AIProviderRouter
from app.core.logging import get_logger
from app.database.connection import get_db
from app.graph.service import KnowledgeGraphService
from app.schemas.graph import (
    EntityConnectionsResponse,
    EntityDetailResponse,
    EntityDocumentResponse,
    EntitySearchResponse,
    GraphOverviewResponse,
    GraphStatsResponse,
    ReprocessGraphRequest,
    ReprocessGraphResponse,
)

logger = get_logger("api.graph")

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])

_ai_router: AIProviderRouter | None = None


def get_ai_router() -> AIProviderRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AIProviderRouter()
    return _ai_router


@router.get(
    "",
    response_model=GraphOverviewResponse,
    summary="Knowledge Graph Overview",
    description="Retrieve bounded nodes and edges with computed 2D positions for visual rendering and navigation.",
)
def get_graph_overview(
    limit_nodes: Annotated[int, Query(ge=1, le=300)] = 50,
    limit_edges: Annotated[int, Query(ge=1, le=600)] = 100,
    type: Annotated[str | None, Query(description="Filter by comma-separated entity types (e.g. Concept,Technology)")] = None,
    rel_type: Annotated[str | None, Query(description="Filter by comma-separated relationship types (e.g. USES,DEVELOPED)")] = None,
    q: Annotated[str | None, Query(description="Search filter substring for entity names")] = None,
    db: Session = Depends(get_db),
) -> GraphOverviewResponse:
    entity_types = {t.strip() for t in type.split(",")} if type and type.lower() != "all" else None
    rel_types = {r.strip() for r in rel_type.split(",")} if rel_type and rel_type.lower() != "all" else None

    service = KnowledgeGraphService(db)
    return service.get_overview(
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
        entity_types=entity_types,
        relationship_types=rel_types,
        query=q,
    )


@router.get(
    "/stats",
    response_model=GraphStatsResponse,
    summary="Knowledge Graph Statistics",
    description="Retrieve high-level graph metrics, entity distributions, relationship types, and density.",
)
def get_graph_stats(
    db: Session = Depends(get_db),
) -> GraphStatsResponse:
    service = KnowledgeGraphService(db)
    return service.get_stats()


@router.get(
    "/search",
    response_model=EntitySearchResponse,
    summary="Search Knowledge Graph Entities",
    description="Search entities by canonical name, normalized keyword, or known aliases.",
)
def search_entities(
    q: Annotated[str, Query(min_length=1, description="Search term")],
    type: Annotated[str | None, Query(description="Filter by entity type")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> EntitySearchResponse:
    entity_types = {t.strip() for t in type.split(",")} if type and type.lower() != "all" else None
    service = KnowledgeGraphService(db)
    return service.search_entities(query=q, entity_types=entity_types, limit=limit)


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetailResponse,
    summary="Get Entity Details",
    description="Retrieve comprehensive details for an entity including aliases, relationships, and supporting documents.",
)
def get_entity_detail(
    entity_id: str,
    db: Session = Depends(get_db),
) -> EntityDetailResponse:
    service = KnowledgeGraphService(db)
    entity_detail = service.get_entity_detail(entity_id)
    if not entity_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' was not found in the Knowledge Graph.",
        )
    return entity_detail


@router.get(
    "/entities/{entity_id}/connections",
    response_model=EntityConnectionsResponse,
    summary="Get Entity Neighborhood Connections",
    description="Explore bounded multi-depth neighborhood graph surrounding a target entity.",
)
def get_entity_connections(
    entity_id: str,
    depth: Annotated[int, Query(ge=1, le=3, description="Traversal depth (1 to 3)")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Max neighbor nodes")] = 50,
    type: Annotated[str | None, Query(description="Filter by entity type")] = None,
    rel_type: Annotated[str | None, Query(description="Filter by relationship type")] = None,
    db: Session = Depends(get_db),
) -> EntityConnectionsResponse:
    entity_types = {t.strip() for t in type.split(",")} if type and type.lower() != "all" else None
    rel_types = {r.strip() for r in rel_type.split(",")} if rel_type and rel_type.lower() != "all" else None

    service = KnowledgeGraphService(db)
    connections = service.get_entity_connections(
        entity_id=entity_id,
        depth=depth,
        max_results=limit,
        entity_types=entity_types,
        relationship_types=rel_types,
    )
    if not connections:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' was not found.",
        )
    return connections


@router.get(
    "/entities/{entity_id}/documents",
    response_model=list[EntityDocumentResponse],
    summary="Get Supporting Documents for Entity",
    description="Retrieve source documents and evidence snippets mentioning this entity with pagination.",
)
def get_entity_documents(
    entity_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[EntityDocumentResponse]:
    service = KnowledgeGraphService(db)
    entity_detail = service.get_entity_detail(entity_id)
    if not entity_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' was not found.",
        )
    return entity_detail.documents[offset : offset + limit]


@router.post(
    "/reprocess",
    response_model=ReprocessGraphResponse,
    summary="Reprocess Graph from Indexed Documents",
    description="Re-extracts entities and relationships for indexed documents without running crawler.",
)
def reprocess_knowledge_graph(
    request: ReprocessGraphRequest,
    db: Session = Depends(get_db),
    ai_router: AIProviderRouter = Depends(get_ai_router),
) -> ReprocessGraphResponse:
    service = KnowledgeGraphService(db)
    result = service.reprocess_all(
        batch_size=request.batch_size,
        use_ai=request.use_ai,
        ai_router=ai_router if request.use_ai else None,
    )
    return ReprocessGraphResponse(
        status=result["status"],
        documents_processed=result["documents_processed"],
        entities_extracted=result["entities_extracted"],
        relationships_extracted=result["relationships_extracted"],
        duration_ms=result["duration_ms"],
    )
