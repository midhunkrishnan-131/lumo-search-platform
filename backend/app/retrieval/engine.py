"""Unified Indexing, Duplicate Detection, Hybrid Retrieval & Search Analytics Engine (Phase 29)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse
import uuid

from sqlalchemy.orm import Session

from app.knowledge_hub.service import KnowledgeHubService
from app.models.evaluation import EvaluationRun
from app.models.retrieval import IndexedRecord
from app.retrieval.chunking import chunk_content
from app.retrieval.embeddings import cached_embedding_provider
from app.retrieval.query_processor import process_query
from app.retrieval.reranker import rerank_candidates
from app.schemas.knowledge_hub import KnowledgeSearchRequest
from app.search.engine import ClassicSearchEngine
from app.search.hybrid import HybridSearchOrchestrator
from app.semantic.search import SemanticSearchEngine


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(url: str | None) -> str:
    clean = (url or "").strip()
    if not clean:
        return ""
    p = urlparse(clean)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", "", p.query, ""))


def _shingle_set(text: str, k: int = 3) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(words) < k:
        return set(words)
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class UnifiedRetrievalEngine:
    """Coordinates unified indexing, duplicate detection, metadata-aware hybrid retrieval, and analytics."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def index_content(
        self,
        title: str,
        content: str,
        source_type: str = "document",
        source_ref_id: str | None = None,
        url: str | None = None,
        content_type: str = "text",
        metadata: dict[str, Any] | None = None,
        owner_id: str = "local",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> dict[str, Any]:
        """Normalize, fingerprint, detect duplicates, chunk, embed, and persist an IndexedRecord."""
        norm_url = normalize_url(url)
        clean_text = " ".join((content or "").split())
        chash = hashlib.sha256(clean_text.encode("utf-8", errors="replace")).hexdigest()
        shingles = _shingle_set(clean_text)
        sig_str = ",".join(sorted(shingles)[:64])

        # Safe duplicate detection (exact hash, URL, or near-duplicate Jaccard >= 0.85) — never auto-deletes
        duplicate_of: str | None = None
        dup_kind: str | None = None
        existing_owned = (
            self.db.query(IndexedRecord)
            .filter(IndexedRecord.owner_id == owner_id, IndexedRecord.status != "failed")
            .all()
        )
        for rec in existing_owned:
            if rec.content_hash == chash:
                duplicate_of, dup_kind = rec.id, "exact"
                break
            if norm_url and rec.normalized_url == norm_url:
                duplicate_of, dup_kind = rec.id, "url"
                break
            rec_sh = set(rec.shingle_sig.split(",")) if rec.shingle_sig else set()
            if shingles and rec_sh and _jaccard(shingles, rec_sh) >= 0.85:
                duplicate_of, dup_kind = rec.id, "near_duplicate"
                break

        rec_id = str(uuid.uuid4())
        chunks = chunk_content(
            content,
            document_id=source_ref_id or rec_id,
            title=title,
            source=norm_url or source_type,
            content_type=content_type,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        # Embed chunks using cached local embedding provider (respects dimension validation)
        if chunks:
            cached_embedding_provider.embed_batch([c.text for c in chunks[:32]])

        rec = IndexedRecord(
            id=rec_id,
            owner_id=owner_id,
            source_type=source_type,
            source_ref_id=source_ref_id,
            title=title.strip()[:500],
            normalized_url=norm_url or None,
            content_hash=chash,
            shingle_sig=sig_str,
            chunk_count=len(chunks),
            status="duplicate_flagged" if duplicate_of else "indexed",
            duplicate_of_id=duplicate_of,
            metadata_json={**(metadata or {}), "content_type": content_type, "duplicate_kind": dup_kind},
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return self._serialize_record(rec)

    def _serialize_record(self, r: IndexedRecord) -> dict[str, Any]:
        return {
            "id": r.id,
            "owner_id": r.owner_id,
            "source_type": r.source_type,
            "source_ref_id": r.source_ref_id,
            "title": r.title,
            "normalized_url": r.normalized_url,
            "content_hash": r.content_hash,
            "chunk_count": r.chunk_count,
            "status": r.status,
            "duplicate_of_id": r.duplicate_of_id,
            "metadata_json": r.metadata_json or {},
            "error_message": r.error_message,
            "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
        }

    def retrieve(
        self,
        query: str,
        owner_id: str = "local",
        mode: str = "hybrid",
        limit: int = 10,
        domain: str | None = None,
        language: str | None = None,
        content_type: str | None = None,
        collection_id: str | None = None,
        tag: str | None = None,
        include_knowledge_hub: bool = True,
        rerank: bool = True,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Execute query-processed, metadata-filtered, hybrid retrieval with reranking & explanations."""
        t0 = time.perf_counter()
        q_info = process_query(query)
        clean_q = q_info["normalized_query"]
        if not clean_q:
            return {"query_analysis": q_info, "total": 0, "results": [], "elapsed_ms": 0.0}

        candidates: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        # 1. Core Search (Classic / Semantic / Hybrid)
        m = (mode or "hybrid").lower()
        if m == "classic":
            sr = ClassicSearchEngine(self.db).search(query=clean_q, page=1, per_page=max(limit, 15), domain=domain, language=language)
            raw_hits = [(r, ["Keyword match"]) for r in sr.results]
        elif m == "semantic":
            sr = SemanticSearchEngine(self.db).search(query=clean_q, page=1, per_page=max(limit, 15), domain=domain, language=language)
            raw_hits = [(r, ["Semantic similarity"]) for r in sr.results]
        else:
            sr, _, _ = HybridSearchOrchestrator(self.db).search(query=clean_q, page=1, per_page=max(limit, 15), domain=domain, language=language)
            raw_hits = []
            for r in sr.results:
                ex = []
                if "classic" in (getattr(r, "sources", None) or []):
                    ex.append("Keyword match")
                if "semantic" in (getattr(r, "sources", None) or []):
                    ex.append("Semantic similarity")
                raw_hits.append((r, ex or ["Hybrid retrieval"]))

        for r, ex in raw_hits:
            rid = getattr(r, "id", "")
            if rid in seen_keys:
                continue
            seen_keys.add(rid)
            candidates.append({
                "id": rid,
                "source_type": "document",
                "url": getattr(r, "url", ""),
                "title": getattr(r, "title", ""),
                "snippet": getattr(r, "snippet", ""),
                "score": float(getattr(r, "score", 0.0) or 0.0),
                "explanations": ex + (["Metadata match"] if (domain or language) else []),
            })

        # 2. Owner-isolated Knowledge Hub retrieval
        if include_knowledge_hub:
            kh_items = KnowledgeHubService(self.db).search_knowledge(
                KnowledgeSearchRequest(query=clean_q, collection_id=collection_id, tag=tag, limit=10),
                owner_id=owner_id,
            )
            for it in kh_items:
                if content_type and it["item_type"].lower() != content_type.lower():
                    continue
                kkey = f"kh:{it['id']}"
                if kkey in seen_keys:
                    continue
                seen_keys.add(kkey)
                ex = ["Knowledge Hub", "Keyword match"]
                if collection_id or tag:
                    ex.append("Metadata match")
                candidates.append({
                    "id": it["id"],
                    "source_type": f"knowledge:{it['item_type']}",
                    "url": it.get("source_url") or "",
                    "title": it["title"],
                    "snippet": (it.get("description") or it.get("content") or "")[:300],
                    "score": 0.6,
                    "explanations": ex,
                })

        final_results = (
            rerank_candidates(clean_q, candidates, top_k=limit, cancel_check=cancel_check)
            if rerank
            else candidates[:limit]
        )
        return {
            "query_analysis": q_info,
            "total": len(final_results),
            "results": final_results,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    def retrieve_for_research(
        self,
        query: str,
        owner_id: str = "local",
        max_sub_queries: int = 3,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Decompose research query into bounded sub-queries and retrieve deduplicated evidence."""
        q_info = process_query(query)
        sub_qs = (q_info["sub_queries"] or [q_info["normalized_query"]])[:max_sub_queries]
        evidence: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sq in sub_qs:
            if cancel_check and cancel_check():
                break
            res = self.retrieve(sq, owner_id=owner_id, mode="hybrid", limit=5, cancel_check=cancel_check)
            for item in res["results"]:
                key = item.get("url") or item.get("id")
                if key not in seen:
                    seen.add(key)
                    item["sub_query"] = sq
                    evidence.append(item)
        return {"sub_queries": sub_qs, "evidence": evidence, "total": len(evidence)}

    def get_index_stats(self, owner_id: str = "local") -> dict[str, Any]:
        recs = self.db.query(IndexedRecord).filter(IndexedRecord.owner_id == owner_id).all()
        by_status: dict[str, int] = {}
        total_chunks = 0
        for r in recs:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            total_chunks += r.chunk_count or 0
        return {
            "total_records": len(recs),
            "total_chunks": total_chunks,
            "by_status": by_status,
            "embedding_cache": cached_embedding_provider.stats(),
        }

    def list_indexed(self, owner_id: str = "local", status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = self.db.query(IndexedRecord).filter(IndexedRecord.owner_id == owner_id)
        if status:
            q = q.filter(IndexedRecord.status == status)
        return [self._serialize_record(r) for r in q.order_by(IndexedRecord.updated_at.desc()).limit(limit).all()]

    def reindex_record(self, record_id: str, owner_id: str = "local") -> dict[str, Any]:
        rec = self.db.query(IndexedRecord).filter(IndexedRecord.id == record_id, IndexedRecord.owner_id == owner_id).first()
        if not rec:
            raise ValueError("Indexed record not found.")
        rec.status = "indexed"
        rec.updated_at = _utc_now()
        self.db.commit()
        return self._serialize_record(rec)

    def delete_index_record(self, record_id: str, owner_id: str = "local", confirm: bool = False) -> bool:
        if not confirm:
            raise ValueError("Index deletion requires confirm=true.")
        rec = self.db.query(IndexedRecord).filter(IndexedRecord.id == record_id, IndexedRecord.owner_id == owner_id).first()
        if not rec:
            return False
        self.db.delete(rec)
        self.db.commit()
        return True

    def get_analytics(self, owner_id: str = "local") -> dict[str, Any]:
        runs = (
            self.db.query(EvaluationRun)
            .filter(EvaluationRun.target_module.in_(["classic_search", "semantic_search", "hybrid_search", "search_comparison"]))
            .order_by(EvaluationRun.started_at.desc())
            .limit(10)
            .all()
        )
        eval_summary = [
            {"run_id": r.id, "target": r.target_module, "metrics": r.metrics_json}
            for r in runs
        ]
        return {
            "index_stats": self.get_index_stats(owner_id=owner_id),
            "search_evaluations": eval_summary,
        }
