"""Evidence Collector: Extracts, sanitizes, and registers session-scoped sources."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.schemas.research import ResearchEvidenceItem
from app.search.engine import SearchResult

logger = get_logger("research.evidence")


class EvidenceCollector:
    """Collects, deduplicates, and manages source mappings for a research session."""

    def __init__(self, max_sources: int = 30) -> None:
        self.max_sources = max_sources
        self.sources_by_id: dict[str, ResearchEvidenceItem] = {}
        self.seen_doc_ids: set[str] = set()
        self.seen_passage_hashes: set[str] = set()
        self._next_source_idx = 1

    def collect(
        self,
        search_results: list[SearchResult],
        query: str,
        iteration: int,
        db: Session,
    ) -> list[ResearchEvidenceItem]:
        """Collect and register new unique sources from search results."""
        newly_collected: list[ResearchEvidenceItem] = []

        for item in search_results:
            if len(self.sources_by_id) >= self.max_sources:
                logger.info("Reached maximum research sources cap (%d)", self.max_sources)
                break

            if item.id in self.seen_doc_ids:
                continue

            # Fetch rich passage from DB if snippet is brief
            passage = item.snippet or item.description
            try:
                doc = db.query(Document).filter(Document.id == item.id).first()
                if doc and hasattr(doc, "main_content") and isinstance(doc.main_content, str):
                    passage = doc.main_content[:600].strip()
            except Exception as exc:
                logger.debug("Could not fetch document content for %s: %s", item.id, exc)

            clean_passage = self._sanitize(str(passage or ""))
            if not clean_passage:
                continue

            norm_key = clean_passage[:80].lower()
            if norm_key in self.seen_passage_hashes:
                continue
            self.seen_passage_hashes.add(norm_key)
            self.seen_doc_ids.add(item.id)

            source_id = f"S{self._next_source_idx}"
            self._next_source_idx += 1

            evidence_item = ResearchEvidenceItem(
                source_id=source_id,
                document_id=item.id,
                title=self._sanitize(item.title) or item.url,
                url=item.url,
                domain=item.domain,
                passage=clean_passage,
                query=query,
                iteration=iteration,
                score=round(item.hybrid_score or item.score, 4),
            )
            self.sources_by_id[source_id] = evidence_item
            newly_collected.append(evidence_item)

        return newly_collected

    def get_all_sources(self) -> list[ResearchEvidenceItem]:
        return list(self.sources_by_id.values())

    def get_source_count(self) -> int:
        return len(self.sources_by_id)

    def get_formatted_context(self, max_tokens: int = 3500) -> str:
        """Format all collected sources into a structured evidence string."""
        char_budget = max_tokens * 4
        current_chars = 0
        blocks = []

        for src in self.sources_by_id.values():
            block = (
                f"[{src.source_id}] {src.title}\n"
                f"URL: {src.url}\n"
                f"Evidence: {src.passage}\n"
            )
            if current_chars + len(block) > char_budget and blocks:
                break
            blocks.append(block)
            current_chars += len(block)

        return "\n---\n".join(blocks)

    def _sanitize(self, text: str) -> str:
        if not text:
            return ""
        # Strip HTML and neutralize prompt injection tokens
        no_html = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"(?i)<\s*(system|instruction|user|assistant)\s*>", "[TAG]", no_html)
        clean = clean.replace("```", "'''")
        return re.sub(r"\s+", " ", clean).strip()

