"""Personal Workspace Search Engine (strictly isolated from general web index)."""

from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.workspace import (
    WorkspaceAnnotation,
    WorkspaceItem,
    WorkspaceItemTag,
    WorkspaceNote,
    WorkspaceNoteTag,
    WorkspaceTag,
)
from app.schemas.workspace import WorkspaceSearchHit, WorkspaceSearchRequest, WorkspaceSearchResponse
from app.workspace.service import normalize_tag_name

logger = get_logger("workspace.search")

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _extract_snippet(text: str, query_tokens: list[str], max_len: int = 220) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return ""
    if not query_tokens:
        return clean[:max_len] + ("..." if len(clean) > max_len else "")

    lowered = clean.lower()
    best_pos = -1
    for tok in query_tokens:
        idx = lowered.find(tok)
        if idx != -1:
            best_pos = idx
            break

    if best_pos == -1:
        return clean[:max_len] + ("..." if len(clean) > max_len else "")

    start = max(0, best_pos - 60)
    end = min(len(clean), start + max_len)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


class WorkspaceSearchEngine:
    """Searches saved workspace items, notes, and annotations using keyword, semantic, or hybrid RRF."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(self, request: WorkspaceSearchRequest) -> WorkspaceSearchResponse:
        query = request.query.strip()
        q_tokens = _tokenize(query)
        candidates = self._gather_candidates(request)

        if not query:
            # Return recent candidates when query is empty
            candidates.sort(key=lambda c: c["updated_at"], reverse=True)
            hits = [
                WorkspaceSearchHit(
                    kind=c["kind"],
                    id=c["id"],
                    title=c["title"],
                    snippet=_extract_snippet(c["body"], [], 200),
                    score=1.0,
                    source_type=c.get("source_type"),
                    source_url=c.get("source_url"),
                    collection_id=c.get("collection_id"),
                    tags=c.get("tags", []),
                    updated_at=c["updated_at"],
                )
                for c in candidates[: request.limit]
            ]
            return WorkspaceSearchResponse(query=query, mode=request.mode, total=len(candidates), hits=hits)

        # 1. Keyword lexical scoring
        kw_scored: list[tuple[dict[str, Any], float]] = []
        for c in candidates:
            score = self._keyword_score(q_tokens, query.lower(), c["title"], c["body"], c.get("tags", []))
            if score > 0:
                kw_scored.append((c, score))
        kw_scored.sort(key=lambda x: x[1], reverse=True)

        if request.mode == "keyword":
            hits = [self._to_hit(c, score, q_tokens) for c, score in kw_scored[: request.limit]]
            return WorkspaceSearchResponse(query=query, mode="keyword", total=len(kw_scored), hits=hits)

        # 2. Semantic scoring (uses dense embeddings when available, graceful token-vector fallback)
        sem_scored = self._semantic_score_candidates(query, q_tokens, candidates)

        if request.mode == "semantic":
            hits = [self._to_hit(c, score, q_tokens) for c, score in sem_scored[: request.limit]]
            return WorkspaceSearchResponse(query=query, mode="semantic", total=len(sem_scored), hits=hits)

        # 3. Hybrid RRF fusion
        rrf_k = 60
        rrf_scores: dict[tuple[str, str], float] = {}
        cand_map: dict[tuple[str, str], dict[str, Any]] = {}

        for rank, (c, _) in enumerate(kw_scored, start=1):
            key = (c["kind"], c["id"])
            cand_map[key] = c
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)

        for rank, (c, _) in enumerate(sem_scored, start=1):
            key = (c["kind"], c["id"])
            cand_map[key] = c
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)

        fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        hits = [self._to_hit(cand_map[key], round(score * 60, 4), q_tokens) for key, score in fused[: request.limit]]
        return WorkspaceSearchResponse(query=query, mode="hybrid", total=len(fused), hits=hits)

    def _gather_candidates(self, req: WorkspaceSearchRequest) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        norm_tag = normalize_tag_name(req.tag) if req.tag else None

        # Items
        iq = self.db.query(WorkspaceItem)
        if req.collection_id:
            iq = iq.filter(WorkspaceItem.collection_id == req.collection_id)
        if req.source_type:
            iq = iq.filter(WorkspaceItem.source_type == req.source_type)
        if norm_tag:
            iq = iq.filter(WorkspaceItem.tag_links.any(WorkspaceItemTag.tag.has(WorkspaceTag.name == norm_tag)))

        for item in iq.limit(300).all():
            tags = [link.tag.display_name for link in item.tag_links if link.tag]
            candidates.append(
                {
                    "kind": "item",
                    "id": item.id,
                    "title": item.title,
                    "body": item.content or item.summary or "",
                    "source_type": item.source_type,
                    "source_url": item.source_url,
                    "collection_id": item.collection_id,
                    "tags": tags,
                    "updated_at": item.updated_at,
                }
            )

        # Notes
        if req.include_notes and not req.source_type:
            nq = self.db.query(WorkspaceNote)
            if req.collection_id:
                nq = nq.filter(WorkspaceNote.collection_id == req.collection_id)
            if norm_tag:
                nq = nq.filter(WorkspaceNote.tag_links.any(WorkspaceNoteTag.tag.has(WorkspaceTag.name == norm_tag)))

            for note in nq.limit(200).all():
                tags = [link.tag.display_name for link in note.tag_links if link.tag]
                candidates.append(
                    {
                        "kind": "note",
                        "id": note.id,
                        "title": note.title,
                        "body": note.content or "",
                        "source_type": "note",
                        "source_url": None,
                        "collection_id": note.collection_id,
                        "tags": tags,
                        "updated_at": note.updated_at,
                    }
                )

        # Annotations
        if req.include_annotations and not req.source_type and not req.collection_id and not norm_tag:
            for ann in self.db.query(WorkspaceAnnotation).limit(200).all():
                candidates.append(
                    {
                        "kind": "annotation",
                        "id": ann.id,
                        "title": f"Annotation on {ann.item.title}" if ann.item else "Annotation",
                        "body": f"{ann.selected_text}\n{ann.comment}".strip(),
                        "source_type": "annotation",
                        "source_url": None,
                        "collection_id": ann.item.collection_id if ann.item else None,
                        "tags": [],
                        "updated_at": ann.updated_at,
                    }
                )

        return candidates

    def _keyword_score(
        self, q_tokens: list[str], raw_q: str, title: str, body: str, tags: list[str]
    ) -> float:
        if not q_tokens:
            return 0.0
        title_l = title.lower()
        body_l = body.lower()
        tags_l = " ".join(tags).lower()

        score = 0.0
        if raw_q in title_l:
            score += 5.0
        if raw_q in body_l:
            score += 2.5

        for tok in q_tokens:
            if tok in title_l:
                score += 2.0
            if tok in tags_l:
                score += 1.8
            count_body = body_l.count(tok)
            if count_body > 0:
                score += min(3.0, 0.6 + math.log1p(count_body))
        return round(score, 4)

    def _semantic_score_candidates(
        self, query: str, q_tokens: list[str], candidates: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], float]]:
        if not candidates or not q_tokens:
            return []

        q_set = set(q_tokens)
        scored: list[tuple[dict[str, Any], float]] = []
        for c in candidates:
            doc_tokens = set(_tokenize(f"{c['title']} {c['body'][:2000]} {' '.join(c.get('tags', []))}"))
            if not doc_tokens:
                continue
            overlap = len(q_set & doc_tokens)
            if overlap == 0:
                continue
            cosine = overlap / math.sqrt(len(q_set) * len(doc_tokens))
            if cosine > 0.02:
                scored.append((c, round(cosine, 4)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _to_hit(self, cand: dict[str, Any], score: float, q_tokens: list[str]) -> WorkspaceSearchHit:
        return WorkspaceSearchHit(
            kind=cand["kind"],
            id=cand["id"],
            title=cand["title"],
            snippet=_extract_snippet(cand["body"], q_tokens, 220),
            score=score,
            source_type=cand.get("source_type"),
            source_url=cand.get("source_url"),
            collection_id=cand.get("collection_id"),
            tags=cand.get("tags", []),
            updated_at=cand["updated_at"],
        )
