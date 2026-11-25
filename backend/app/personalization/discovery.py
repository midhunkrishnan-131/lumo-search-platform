"""Personalized Discovery Engine grounded strictly in existing LUMO data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.graph import Entity
from app.models.personalization import TopicProfile, UserInterest
from app.models.workspace import WorkspaceItem
from app.schemas.personalization import RecommendationItem


class DiscoveryEngine:
    """Recommends related topics, workspace items, graph entities, and indexed docs with reasons."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_recommendations(self, limit: int = 12) -> list[RecommendationItem]:
        interests = (
            self.db.query(UserInterest)
            .filter(UserInterest.source.in_(["explicit", "followed"]))
            .order_by(UserInterest.weight.desc())
            .limit(8)
            .all()
        )
        topics = (
            self.db.query(TopicProfile)
            .filter(TopicProfile.signal_kind.in_(["repeated", "explicit", "curiosity"]))
            .order_by(TopicProfile.frequency.desc(), TopicProfile.last_seen_at.desc())
            .limit(8)
            .all()
        )
        excluded_norms = {
            i.normalized_topic
            for i in self.db.query(UserInterest).filter(UserInterest.source == "excluded").all()
        }

        seed_terms = []
        for i in interests:
            seed_terms.append((i.topic, i.normalized_topic, "Followed interest"))
        for t in topics:
            if t.normalized_topic not in {s[1] for s in seed_terms}:
                label = "Frequently explored topic" if t.signal_kind in ("repeated", "explicit") else "Recent search topic"
                seed_terms.append((t.topic, t.normalized_topic, label))

        recs: list[RecommendationItem] = []
        seen_ids: set[tuple[str, str]] = set()

        # 1. Knowledge Graph Entities matching user topics
        if seed_terms:
            entities = self.db.query(Entity).limit(60).all()
            for ent in entities:
                if ent.normalized_name in excluded_norms:
                    continue
                for orig_topic, norm_t, reason_prefix in seed_terms:
                    if norm_t in ent.normalized_name or ent.normalized_name in norm_t:
                        key = ("graph_entity", ent.id)
                        if key not in seen_ids:
                            seen_ids.add(key)
                            recs.append(
                                RecommendationItem(
                                    kind="graph_entity",
                                    id=ent.id,
                                    title=f"{ent.name} ({ent.entity_type})",
                                    reason=f"Connected to Knowledge Graph entity matching '{orig_topic}'",
                                    signals=[reason_prefix, "knowledge_graph"],
                                    score=0.9,
                                )
                            )
                        break

        # 2. Personal Workspace items related to user topics
        ws_items = self.db.query(WorkspaceItem).order_by(WorkspaceItem.created_at.desc()).limit(30).all()
        for item in ws_items:
            hay = f"{item.title} {item.summary or ''}".lower()
            if any(exc in hay for exc in excluded_norms):
                continue
            for orig_topic, norm_t, reason_prefix in seed_terms:
                if norm_t in hay:
                    key = ("workspace_item", item.id)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        recs.append(
                            RecommendationItem(
                                kind="workspace_item",
                                id=item.id,
                                title=item.title,
                                url=item.source_url,
                                reason=f"Related to your saved Workspace item on '{orig_topic}'",
                                signals=[reason_prefix, "workspace"],
                                score=0.85,
                            )
                        )
                    break

        # 3. Indexed Documents matching user topics
        docs = (
            self.db.query(Document)
            .filter(Document.is_duplicate == False)  # noqa: E712
            .order_by(Document.created_at.desc())
            .limit(40)
            .all()
        )
        for doc in docs:
            hay = f"{doc.title or ''} {doc.description or ''}".lower()
            if any(exc in hay for exc in excluded_norms):
                continue
            for orig_topic, norm_t, reason_prefix in seed_terms:
                if norm_t in hay:
                    key = ("indexed_document", doc.id)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        recs.append(
                            RecommendationItem(
                                kind="indexed_document",
                                id=doc.id,
                                title=doc.title or doc.url,
                                url=doc.url,
                                reason=f"Indexed in LUMO and matches '{orig_topic}'",
                                signals=[reason_prefix, "indexed_content"],
                                score=0.8,
                            )
                        )
                    break

        # 4. Suggested Research Topics based on interests
        for orig_topic, norm_t, reason_prefix in seed_terms[:3]:
            key = ("research_topic", norm_t)
            if key not in seen_ids:
                seen_ids.add(key)
                recs.append(
                    RecommendationItem(
                        kind="research_topic",
                        id=norm_t,
                        title=f"Deep Research: {orig_topic}",
                        reason=f"Suggested research topic ({reason_prefix.lower()})",
                        signals=[reason_prefix],
                        score=0.7,
                    )
                )

        recs.sort(key=lambda r: -r.score)
        return recs[:limit]
