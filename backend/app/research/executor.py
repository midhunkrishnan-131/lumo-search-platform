"""Research Executor: Runs deduplicated queries against LUMO Hybrid Search."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.search.engine import SearchResult
from app.search.hybrid import HybridSearchOrchestrator

logger = get_logger("research.executor")


class ResearchExecutor:
    """Coordinates search execution across iterations with query and document deduplication."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.hybrid_orchestrator = HybridSearchOrchestrator(db)
        self.executed_queries: set[str] = set()

    def execute_query(
        self,
        query: str,
        iteration: int,
        limit: int = 6,
    ) -> list[SearchResult]:
        """Execute a single query if not already executed in this session."""
        norm_query = query.strip().lower()
        if not norm_query or norm_query in self.executed_queries:
            logger.debug("Skipping duplicate or empty query: %s", query)
            return []

        self.executed_queries.add(norm_query)
        logger.info("Executing research query (iteration %d): '%s'", iteration, query)

        try:
            search_set, _, _ = self.hybrid_orchestrator.search(
                query=query,
                page=1,
                per_page=limit,
            )
            return search_set.results
        except Exception as exc:
            logger.warning("Query execution failed for '%s': %s", query, exc)
            return []
