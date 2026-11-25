"""Knowledge Graph service coordinating persistence, NetworkX indexing, and queries."""

from __future__ import annotations

import threading
import time
from typing import Any
import uuid

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.graph.engine import KnowledgeGraphEngine
from app.graph.extractor import EntityExtractor, ExtractedEntity
from app.graph.normalizer import EntityNormalizer, normalize_entity_name
from app.graph.relationships import ExtractedRelationship, RelationshipExtractor
from app.models.document import Document
from app.models.graph import (
    Entity,
    EntityAlias,
    EntityDocument,
    EntityResolutionLog,
    Relationship,
    RelationshipEvidence,
)
from app.schemas.graph import (
    EntityConnectionsResponse,
    EntityDetailResponse,
    EntityDocumentResponse,
    EntityResponse,
    EntitySearchResponse,
    GraphEdge,
    GraphNode,
    GraphOverviewResponse,
    GraphStatsResponse,
    RelationshipEvidenceResponse,
    RelationshipResponse,
)

logger = get_logger("graph.service")

_CACHE_LOCK = threading.Lock()
_GRAPH_CACHE: dict[tuple[str, int, int], KnowledgeGraphEngine] = {}


def invalidate_graph_cache() -> None:
    """Clear the cached Knowledge Graph engine instances."""
    with _CACHE_LOCK:
        _GRAPH_CACHE.clear()


class KnowledgeGraphService:
    """Coordinates Knowledge Graph persistence in PostgreSQL/SQLite and NetworkX graph analysis."""

    def __init__(self, db: Session, normalizer: EntityNormalizer | None = None) -> None:
        self.db = db
        self.normalizer = normalizer or EntityNormalizer()
        self.extractor = EntityExtractor(normalizer=self.normalizer)
        self.rel_extractor = RelationshipExtractor()
        self.engine = KnowledgeGraphEngine()
        self._load_engine()

    def _get_cache_key(self) -> tuple[str, int, int]:
        bind_id = str(id(self.db.get_bind()))
        ent_count = self.db.query(func.count(Entity.id)).scalar() or 0
        rel_count = self.db.query(func.count(Relationship.id)).scalar() or 0
        return (bind_id, ent_count, rel_count)

    def _load_engine(self, force_reload: bool = False) -> None:
        """Load persisted entities and relationships into the NetworkX engine with caching."""
        try:
            cache_key = self._get_cache_key()
            if not force_reload:
                with _CACHE_LOCK:
                    cached = _GRAPH_CACHE.get(cache_key)
                    if cached is not None:
                        self.engine = cached
                        return

            self.engine = KnowledgeGraphEngine()
            entities = self.db.query(Entity).all()
            if not entities:
                with _CACHE_LOCK:
                    _GRAPH_CACHE[cache_key] = self.engine
                return

            # Count source documents per entity
            doc_counts = dict(
                self.db.query(EntityDocument.entity_id, func.count(EntityDocument.id))
                .group_by(EntityDocument.entity_id)
                .all()
            )

            for ent in entities:
                self.engine.add_entity_node(
                    entity_id=ent.id,
                    name=ent.name,
                    entity_type=ent.entity_type,
                    description=ent.description,
                    confidence=ent.confidence,
                    sources_count=doc_counts.get(ent.id, 0),
                )

            relationships = self.db.query(Relationship).all()
            evidence_counts = dict(
                self.db.query(RelationshipEvidence.relationship_id, func.count(RelationshipEvidence.id))
                .group_by(RelationshipEvidence.relationship_id)
                .all()
            )

            # Batch load first snippets in 1 query (eliminates N+1 query)
            first_snippets: dict[str, str] = {}
            for rel_id, snippet in self.db.query(
                RelationshipEvidence.relationship_id, RelationshipEvidence.snippet
            ).all():
                if rel_id not in first_snippets and snippet:
                    first_snippets[rel_id] = snippet

            for rel in relationships:
                self.engine.add_relationship_edge(
                    edge_id=rel.id,
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    relationship_type=rel.relationship_type,
                    weight=rel.weight,
                    confidence=rel.confidence,
                    evidence_count=evidence_counts.get(rel.id, 1),
                    first_snippet=first_snippets.get(rel.id),
                )

            self.engine.compute_layout()
            with _CACHE_LOCK:
                # Keep cache bounded to at most 4 binds
                if len(_GRAPH_CACHE) >= 4:
                    _GRAPH_CACHE.clear()
                _GRAPH_CACHE[cache_key] = self.engine
            logger.info("Knowledge Graph loaded with %d nodes and %d edges", len(entities), len(relationships))
        except Exception as exc:
            logger.warning("Error loading NetworkX graph engine: %s", exc)

    def index_document(
        self,
        document_id: str,
        ai_router: Any = None,
        use_ai: bool = False,
    ) -> tuple[int, int]:
        """Extract and persist entities and relationships from a single document.

        Returns:
            Tuple of (entities_count, relationships_count)
        """
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.main_content:
            return 0, 0

        # 1. Entity Extraction
        if use_ai and ai_router:
            extracted_entities = self.extractor.extract_with_ai(
                text=doc.main_content,
                ai_router=ai_router,
                title=doc.title,
            )
        else:
            extracted_entities = self.extractor.extract(
                text=doc.main_content,
                title=doc.title,
                headings=doc.headings if isinstance(doc.headings, list) else None,
            )

        if not extracted_entities:
            return 0, 0

        # Persist Entities and EntityDocument records
        entity_db_map: dict[str, Entity] = {}  # norm -> Entity

        for ee in extracted_entities:
            # Check existing entity by normalized_name & entity_type
            db_entity = (
                self.db.query(Entity)
                .filter(
                    Entity.normalized_name == ee.normalized_name,
                    Entity.entity_type == ee.entity_type,
                )
                .first()
            )

            if not db_entity:
                db_entity = Entity(
                    id=str(uuid.uuid4()),
                    name=ee.name,
                    normalized_name=ee.normalized_name,
                    entity_type=ee.entity_type,
                    description=ee.first_snippet,
                    confidence=ee.confidence,
                    extraction_method=ee.extraction_method,
                )
                self.db.add(db_entity)
                self.db.flush()

            entity_db_map[ee.normalized_name] = db_entity

            # Persist aliases
            for alias in ee.aliases:
                alias_norm = normalize_entity_name(alias)
                if alias_norm and alias_norm != ee.normalized_name:
                    existing_alias = (
                        self.db.query(EntityAlias)
                        .filter(
                            EntityAlias.entity_id == db_entity.id,
                            EntityAlias.normalized_alias == alias_norm,
                        )
                        .first()
                    )
                    if not existing_alias:
                        self.db.add(
                            EntityAlias(
                                entity_id=db_entity.id,
                                alias=alias,
                                normalized_alias=alias_norm,
                            )
                        )

            # Link Entity to Document
            existing_ed = (
                self.db.query(EntityDocument)
                .filter(
                    EntityDocument.entity_id == db_entity.id,
                    EntityDocument.document_id == doc.id,
                )
                .first()
            )
            if existing_ed:
                existing_ed.mention_count += 1
            else:
                self.db.add(
                    EntityDocument(
                        entity_id=db_entity.id,
                        document_id=doc.id,
                        mention_count=1,
                        confidence=ee.confidence,
                        first_snippet=ee.first_snippet,
                    )
                )

        self.db.flush()

        # 2. Relationship Extraction
        extracted_rels = self.rel_extractor.extract(
            text=doc.main_content,
            entities=extracted_entities,
        )

        persisted_rel_count = 0
        for er in extracted_rels:
            src_norm = normalize_entity_name(er.source_name)
            tgt_norm = normalize_entity_name(er.target_name)

            src_entity = entity_db_map.get(src_norm)
            tgt_entity = entity_db_map.get(tgt_norm)

            if not src_entity or not tgt_entity or src_entity.id == tgt_entity.id:
                continue

            # Check existing relationship
            db_rel = (
                self.db.query(Relationship)
                .filter(
                    Relationship.source_id == src_entity.id,
                    Relationship.target_id == tgt_entity.id,
                    Relationship.relationship_type == er.relationship_type,
                )
                .first()
            )

            if not db_rel:
                db_rel = Relationship(
                    id=str(uuid.uuid4()),
                    source_id=src_entity.id,
                    target_id=tgt_entity.id,
                    relationship_type=er.relationship_type,
                    confidence=er.confidence,
                    extraction_method=er.extraction_method,
                    weight=1.0,
                )
                self.db.add(db_rel)
                self.db.flush()
                persisted_rel_count += 1
            else:
                db_rel.weight += 1.0

            # Attach evidence snippet
            existing_ev = (
                self.db.query(RelationshipEvidence)
                .filter(
                    RelationshipEvidence.relationship_id == db_rel.id,
                    RelationshipEvidence.document_id == doc.id,
                )
                .first()
            )
            if not existing_ev and er.snippet:
                self.db.add(
                    RelationshipEvidence(
                        relationship_id=db_rel.id,
                        document_id=doc.id,
                        snippet=er.snippet,
                    )
                )

        self.db.commit()
        # Refresh in-memory NetworkX model
        self._load_engine(force_reload=True)
        return len(extracted_entities), persisted_rel_count

    def delete_document_entities(self, document_id: str) -> None:
        """Remove associations when a document is deleted, cleaning up orphaned nodes/edges."""
        self.db.query(EntityDocument).filter(EntityDocument.document_id == document_id).delete()
        self.db.query(RelationshipEvidence).filter(RelationshipEvidence.document_id == document_id).delete()

        # Clean orphaned relationships with no evidence
        orphaned_rels = (
            self.db.query(Relationship)
            .outerjoin(RelationshipEvidence, Relationship.id == RelationshipEvidence.relationship_id)
            .filter(RelationshipEvidence.id == None)  # noqa: E711
            .all()
        )
        for rel in orphaned_rels:
            self.db.delete(rel)

        # Clean orphaned entities with no documents
        orphaned_entities = (
            self.db.query(Entity)
            .outerjoin(EntityDocument, Entity.id == EntityDocument.entity_id)
            .filter(EntityDocument.id == None)  # noqa: E711
            .all()
        )
        for ent in orphaned_entities:
            self.db.delete(ent)

        self.db.commit()
        self._load_engine(force_reload=True)

    def reprocess_all(self, batch_size: int = 50, use_ai: bool = False, ai_router: Any = None) -> dict[str, Any]:
        """Reprocess knowledge graph extraction for all non-duplicate indexed documents."""
        start_t = time.perf_counter()
        docs = (
            self.db.query(Document)
            .filter(Document.is_duplicate == False)  # noqa: E712
            .limit(batch_size)
            .all()
        )

        total_ent = 0
        total_rel = 0

        for doc in docs:
            e_count, r_count = self.index_document(doc.id, ai_router=ai_router, use_ai=use_ai)
            total_ent += e_count
            total_rel += r_count

        duration = round((time.perf_counter() - start_t) * 1000, 2)
        return {
            "status": "completed",
            "documents_processed": len(docs),
            "entities_extracted": total_ent,
            "relationships_extracted": total_rel,
            "duration_ms": duration,
        }

    def get_overview(
        self,
        limit_nodes: int = 50,
        limit_edges: int = 100,
        entity_types: set[str] | None = None,
        relationship_types: set[str] | None = None,
        query: str | None = None,
    ) -> GraphOverviewResponse:
        """Produce filtered, bounded graph overview with computed 2D positions."""
        nodes: list[GraphNode] = []
        node_ids: set[str] = set()

        q_lower = query.strip().lower() if query else None

        for nid, data in self.engine.graph.nodes(data=True):
            if entity_types and data.get("type") not in entity_types:
                continue
            if q_lower and q_lower not in data.get("label", "").lower():
                continue

            nodes.append(
                GraphNode(
                    id=nid,
                    label=data.get("label", nid),
                    type=data.get("type", "Concept"),
                    description=data.get("description"),
                    degree=self.engine.graph.degree(nid),
                    confidence=data.get("confidence", 1.0),
                    x=data.get("x"),
                    y=data.get("y"),
                    sources_count=data.get("sources_count", 0),
                )
            )
            node_ids.add(nid)
            if len(nodes) >= limit_nodes:
                break

        edges: list[GraphEdge] = []
        for u, v, k, ed in self.engine.graph.edges(keys=True, data=True):
            if u not in node_ids or v not in node_ids:
                continue
            if relationship_types and ed.get("label") not in relationship_types:
                continue

            edges.append(
                GraphEdge(
                    id=ed.get("id", k),
                    **{"from": u},
                    to=v,
                    label=ed.get("label", "RELATED_TO"),
                    weight=ed.get("weight", 1.0),
                    confidence=ed.get("confidence", 1.0),
                    evidence_count=ed.get("evidence_count", 1),
                    first_snippet=ed.get("first_snippet"),
                )
            )
            if len(edges) >= limit_edges:
                break

        return GraphOverviewResponse(
            nodes=nodes,
            edges=edges,
            total_nodes=len(self.engine.graph),
            total_edges=self.engine.graph.number_of_edges(),
            truncated=(len(nodes) < len(self.engine.graph)),
        )

    def get_entity_detail(self, entity_id: str) -> EntityDetailResponse | None:
        """Fetch complete entity detail including aliases, relationships, and document evidence."""
        ent = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not ent:
            return None

        aliases = [a.alias for a in ent.aliases]

        # Gather relationships
        rels: list[RelationshipResponse] = []
        db_rels = (
            self.db.query(Relationship)
            .filter(or_(Relationship.source_id == ent.id, Relationship.target_id == ent.id))
            .limit(50)
            .all()
        )

        for r in db_rels:
            evidences = [
                RelationshipEvidenceResponse(
                    id=ev.id,
                    relationship_id=ev.relationship_id,
                    document_id=ev.document_id,
                    snippet=ev.snippet,
                    document_title=ev.document.title if ev.document else None,
                    document_url=ev.document.url if ev.document else None,
                    created_at=ev.created_at,
                )
                for ev in r.evidence
            ]

            rels.append(
                RelationshipResponse(
                    id=r.id,
                    source_id=r.source_id,
                    target_id=r.target_id,
                    source_name=r.source_entity.name if r.source_entity else None,
                    target_name=r.target_entity.name if r.target_entity else None,
                    relationship_type=r.relationship_type,
                    confidence=r.confidence,
                    extraction_method=r.extraction_method,
                    weight=r.weight,
                    created_at=r.created_at,
                    evidence=evidences,
                )
            )

        # Gather documents
        docs: list[EntityDocumentResponse] = [
            EntityDocumentResponse(
                id=ed.id,
                entity_id=ed.entity_id,
                document_id=ed.document_id,
                mention_count=ed.mention_count,
                confidence=ed.confidence,
                first_snippet=ed.first_snippet,
                document_title=ed.document.title if ed.document else None,
                document_url=ed.document.url if ed.document else None,
                created_at=ed.created_at,
            )
            for ed in ent.documents
        ]

        degree = self.engine.graph.degree(ent.id) if self.engine.graph.has_node(ent.id) else len(rels)

        return EntityDetailResponse(
            id=ent.id,
            name=ent.name,
            normalized_name=ent.normalized_name,
            entity_type=ent.entity_type,
            description=ent.description,
            confidence=ent.confidence,
            extraction_method=ent.extraction_method,
            created_at=ent.created_at,
            updated_at=ent.updated_at,
            mention_count=sum(ed.mention_count for ed in docs),
            degree=degree,
            aliases=aliases,
            relationships=rels,
            documents=docs,
        )

    def get_entity_connections(
        self,
        entity_id: str,
        depth: int = 1,
        max_results: int = 50,
        entity_types: set[str] | None = None,
        relationship_types: set[str] | None = None,
    ) -> EntityConnectionsResponse | None:
        """Fetch bounded neighborhood connections for a specific entity."""
        ent = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not ent:
            return None

        nbr_nodes, nbr_edges = self.engine.get_neighborhood(
            entity_id=entity_id,
            max_depth=depth,
            max_nodes=max_results,
            entity_types=entity_types,
            relationship_types=relationship_types,
        )

        nodes_out = [
            GraphNode(
                id=n["id"],
                label=n["label"],
                type=n.get("type", "Concept"),
                description=n.get("description"),
                degree=n.get("degree", 0),
                confidence=n.get("confidence", 1.0),
                x=n.get("x"),
                y=n.get("y"),
                sources_count=n.get("sources_count", 0),
            )
            for n in nbr_nodes
        ]

        edges_out = [
            GraphEdge(
                id=e["id"],
                **{"from": e["from"]},
                to=e["to"],
                label=e["label"],
                weight=e.get("weight", 1.0),
                confidence=e.get("confidence", 1.0),
                evidence_count=e.get("evidence_count", 1),
                first_snippet=e.get("first_snippet"),
            )
            for e in nbr_edges
        ]

        entity_resp = EntityResponse(
            id=ent.id,
            name=ent.name,
            normalized_name=ent.normalized_name,
            entity_type=ent.entity_type,
            description=ent.description,
            confidence=ent.confidence,
            extraction_method=ent.extraction_method,
            created_at=ent.created_at,
            updated_at=ent.updated_at,
            degree=self.engine.graph.degree(ent.id) if self.engine.graph.has_node(ent.id) else 0,
        )

        return EntityConnectionsResponse(
            entity=entity_resp,
            depth=depth,
            nodes=nodes_out,
            edges=edges_out,
        )

    def search_entities(
        self,
        query: str,
        entity_types: set[str] | None = None,
        limit: int = 20,
    ) -> EntitySearchResponse:
        """Search entities by name, normalized name, or alias."""
        clean_q = query.strip()
        norm_q = normalize_entity_name(clean_q)

        q = self.db.query(Entity)
        if clean_q:
            q = q.filter(
                or_(
                    Entity.name.ilike(f"%{clean_q}%"),
                    Entity.normalized_name.ilike(f"%{norm_q}%"),
                    Entity.aliases.any(EntityAlias.alias.ilike(f"%{clean_q}%")),
                )
            )

        if entity_types:
            q = q.filter(Entity.entity_type.in_(entity_types))

        total = q.count()
        entities = q.order_by(Entity.name.asc()).limit(limit).all()

        items = [
            EntityResponse(
                id=ent.id,
                name=ent.name,
                normalized_name=ent.normalized_name,
                entity_type=ent.entity_type,
                description=ent.description,
                confidence=ent.confidence,
                extraction_method=ent.extraction_method,
                created_at=ent.created_at,
                updated_at=ent.updated_at,
                degree=self.engine.graph.degree(ent.id) if self.engine.graph.has_node(ent.id) else 0,
            )
            for ent in entities
        ]

        return EntitySearchResponse(query=clean_q, total=total, items=items)

    def get_stats(self) -> GraphStatsResponse:
        """Fetch comprehensive graph and document association statistics."""
        engine_stats = self.engine.get_stats()
        doc_count = self.db.query(func.count(func.distinct(EntityDocument.document_id))).scalar() or 0

        return GraphStatsResponse(
            total_entities=engine_stats["total_entities"],
            entities_by_type=engine_stats["entities_by_type"],
            total_relationships=engine_stats["total_relationships"],
            relationships_by_type=engine_stats["relationships_by_type"],
            total_documents_represented=doc_count,
            graph_density=engine_stats["graph_density"],
            top_connected_entities=engine_stats["top_connected_entities"],
        )
