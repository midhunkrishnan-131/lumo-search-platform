"""Hybrid Search Orchestrator combining PostgreSQL Classic Search and Qdrant Semantic Search with RRF."""

from __future__ import annotations

import copy
import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import get_logger
from app.search.engine import ClassicSearchEngine, SearchResult, SearchResultSet
from app.semantic.search import SemanticSearchEngine

logger = get_logger("search.hybrid")


def reciprocal_rank_fusion(
    classic_items: list[SearchResult],
    semantic_items: list[SearchResult],
    k: int = 60,
) -> list[SearchResult]:
    """Fuse Classic and Semantic retrieval results using Reciprocal Rank Fusion (RRF).

    RRF Score = Sum_m ( 1.0 / (k + rank_m) )

    Args:
        classic_items: Ordered list of results from keyword retrieval.
        semantic_items: Ordered list of results from vector similarity retrieval.
        k: Smoothing constant (default 60).

    Returns:
        Deduplicated list of SearchResult items ranked by fused hybrid_score descending.
    """
    fused_map: dict[str, SearchResult] = {}

    # 1. Process Classic results with 1-based rank
    for rank, item in enumerate(classic_items, start=1):
        rrf_contrib = 1.0 / (k + rank)
        fused_item = copy.copy(item)
        fused_item.classic_rank = rank
        fused_item.semantic_rank = None
        fused_item.sources = ["classic"]
        fused_item.hybrid_score = round(rrf_contrib, 6)
        fused_item.score = fused_item.hybrid_score
        fused_map[item.id] = fused_item

    # 2. Process Semantic results with 1-based rank
    for rank, item in enumerate(semantic_items, start=1):
        rrf_contrib = 1.0 / (k + rank)
        if item.id in fused_map:
            # Document discovered by both retrieval methods
            existing = fused_map[item.id]
            existing.semantic_rank = rank
            existing.sources = ["classic", "semantic"]
            existing.hybrid_score = round(existing.hybrid_score + rrf_contrib, 6)
            existing.score = existing.hybrid_score

            # Snippet preference: prefer snippet with active highlighted matches
            if ("<b>" in item.snippet or "<mark>" in item.snippet) and not ("<b>" in existing.snippet or "<mark>" in existing.snippet):
                existing.snippet = item.snippet
            elif len(item.snippet) > len(existing.snippet) and not ("<b>" in existing.snippet):
                existing.snippet = item.snippet
        else:
            # Document discovered by Semantic Search only
            fused_item = copy.copy(item)
            fused_item.classic_rank = None
            fused_item.semantic_rank = rank
            fused_item.sources = ["semantic"]
            fused_item.hybrid_score = round(rrf_contrib, 6)
            fused_item.score = fused_item.hybrid_score
            fused_map[item.id] = fused_item

    # 3. Sort by hybrid_score descending; tie-breaker: best individual rank
    def _sort_key(res: SearchResult) -> tuple[float, int]:
        best_rank = 9999
        if res.classic_rank is not None:
            best_rank = min(best_rank, res.classic_rank)
        if res.semantic_rank is not None:
            best_rank = min(best_rank, res.semantic_rank)
        return (res.hybrid_score or 0.0, -best_rank)

    fused_list = sorted(fused_map.values(), key=_sort_key, reverse=True)
    return fused_list


class HybridSearchOrchestrator:
    """Coordinates parallel/sequential keyword and semantic retrieval, RRF fusion, and graceful degradation."""

    def __init__(
        self,
        db: Session,
        rrf_k: int | None = None,
        classic_depth: int | None = None,
        semantic_depth: int | None = None,
    ) -> None:
        self.db = db
        settings = get_settings()
        self.rrf_k = rrf_k or settings.hybrid_rrf_k
        self.classic_depth = classic_depth or settings.hybrid_classic_depth
        self.semantic_depth = semantic_depth or settings.hybrid_semantic_depth

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 8,
        domain: str | None = None,
        language: str | None = None,
        k: int | None = None,
    ) -> tuple[SearchResultSet, bool, dict[str, str | int | float | bool]]:
        """Execute hybrid search pipeline.

        Returns:
            Tuple of (SearchResultSet, degraded_boolean, execution_metadata_dict)
        """
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page
        effective_k = k or self.rrf_k

        clean_query = self._normalize_query(query)
        if not clean_query:
            empty_set = SearchResultSet(
                query=query,
                mode="hybrid",
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                results=[],
            )
            return empty_set, False, {"status": "empty_query"}

        classic_items: list[SearchResult] = []
        semantic_items: list[SearchResult] = []
        classic_failed = False
        semantic_failed = False

        # 1. Classic Search Retrieval
        try:
            classic_engine = ClassicSearchEngine(self.db)
            c_res = classic_engine.search(
                query=clean_query,
                page=1,
                per_page=self.classic_depth,
                domain=domain,
                language=language,
            )
            classic_items = c_res.results
        except Exception as exc:
            logger.warning("Classic retrieval failed in hybrid pipeline: %s", exc)
            classic_failed = True

        # 2. Semantic Search Retrieval
        try:
            semantic_engine = SemanticSearchEngine(self.db)
            s_res = semantic_engine.search(
                query=clean_query,
                page=1,
                per_page=self.semantic_depth,
                domain=domain,
                language=language,
            )
            semantic_items = s_res.results
        except Exception as exc:
            logger.warning("Semantic retrieval failed in hybrid pipeline: %s", exc)
            semantic_failed = True

        degraded = classic_failed or semantic_failed

        # 3. Rank Fusion & Deduplication
        fused_results = reciprocal_rank_fusion(
            classic_items=classic_items,
            semantic_items=semantic_items,
            k=effective_k,
        )

        total = len(fused_results)
        total_pages = max(1, (total + per_page - 1) // per_page)
        paginated = fused_results[offset : offset + per_page]

        both_count = sum(1 for r in fused_results if "classic" in r.sources and "semantic" in r.sources)

        metadata: dict[str, str | int | float | bool] = {
            "classic_retrieved": len(classic_items),
            "semantic_retrieved": len(semantic_items),
            "fused_total": total,
            "both_sources_count": both_count,
            "rrf_k": effective_k,
            "degraded": degraded,
            "classic_failed": classic_failed,
            "semantic_failed": semantic_failed,
        }

        search_set = SearchResultSet(
            query=query,
            mode="hybrid",
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            results=paginated,
        )

        return search_set, degraded, metadata

    def _normalize_query(self, query: str) -> str:
        if not query:
            return ""
        cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", query)
        return re.sub(r"\s+", " ", cleaned).strip()[:400]
