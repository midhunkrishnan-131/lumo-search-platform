"""Context builder and source manager for LUMO AI Search RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.search.engine import SearchResult

logger = get_logger("ai.context")


@dataclass
class ContextSource:
    """Internal representation of a context document mapped to a stable reference ID."""

    source_id: str  # e.g. "S1", "S2"
    document_id: str
    title: str
    url: str
    domain: str
    snippet: str
    content: str
    retrieval_score: float = 0.0
    sources: list[str] = field(default_factory=list)


@dataclass
class ContextResult:
    """Result payload produced by the ContextBuilder."""

    formatted_context: str
    sources: list[ContextSource]
    source_map: dict[str, ContextSource]
    total_tokens_approx: int
    has_sufficient_evidence: bool


class ContextBuilder:
    """Constructs prompt-injection-safe evidence blocks from retrieved search documents."""

    def __init__(
        self,
        max_documents: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        self.max_documents = max_documents or settings.ai_max_context_documents
        self.max_tokens = max_tokens or settings.ai_max_context_tokens

    def build_context(
        self,
        search_items: list[SearchResult],
        query: str = "",
        db: Session | None = None,
    ) -> ContextResult:
        """Select, deduplicate, sanitize, and format search items into an evidence package.

        Args:
            search_items: Ranked results from Hybrid Search.
            query: User search query for relevance checking.
            db: Optional database session to fetch full content if snippet is short.

        Returns:
            ContextResult containing formatted prompt context and source mapping.
        """
        if not search_items:
            return ContextResult(
                formatted_context="",
                sources=[],
                source_map={},
                total_tokens_approx=0,
                has_sufficient_evidence=False,
            )

        selected_items = search_items[: self.max_documents]
        sources: list[ContextSource] = []
        source_map: dict[str, ContextSource] = {}

        # Rough token approximation: 1 token ~= 4 characters in English
        char_budget = self.max_tokens * 4
        current_chars = 0
        seen_texts: set[str] = set()

        for idx, item in enumerate(selected_items, start=1):
            source_id = f"S{idx}"

            # Fetch main content from DB if snippet is short and session is provided
            content_text = item.snippet or item.description
            if db and len(content_text) < 200:
                try:
                    doc = db.query(Document).filter(Document.id == item.id).first()
                    if doc and doc.main_content:
                        # Grab first ~800 chars of main content
                        content_text = doc.main_content[:800].strip()
                except Exception as exc:
                    logger.debug("Could not fetch extra document text: %s", exc)

            # Sanitize prompt injection first so [TAG] replaces <system> before HTML stripping
            safe_raw = self._sanitize_for_prompt(content_text)
            clean_passage = self._clean_text(safe_raw)

            # Deduplication of identical passages
            norm_key = clean_passage[:100].lower()
            if norm_key in seen_texts:
                continue
            seen_texts.add(norm_key)

            safe_title = self._clean_text(self._sanitize_for_prompt(item.title))

            # Check character budget
            item_char_len = len(safe_title) + len(clean_passage) + 100
            if current_chars + item_char_len > char_budget and sources:
                # Truncate content to fit remaining budget if possible
                remaining = char_budget - current_chars - 100
                if remaining > 150:
                    clean_passage = clean_passage[:remaining] + "..."
                else:
                    break

            ctx_src = ContextSource(
                source_id=source_id,
                document_id=item.id,
                title=safe_title,
                url=item.url,
                domain=item.domain,
                snippet=item.snippet,
                content=clean_passage,
                retrieval_score=item.hybrid_score or item.score,
                sources=item.sources,
            )
            sources.append(ctx_src)
            source_map[source_id] = ctx_src
            current_chars += len(clean_passage) + len(safe_title) + 100

        # Format evidence block with clear untrusted boundaries
        evidence_lines = []
        for src in sources:
            evidence_lines.append(
                f"[{src.source_id}]\n"
                f"Title: {src.title}\n"
                f"URL: {src.url}\n"
                f"Evidence: {src.content}\n"
            )

        formatted_context = "\n---\n".join(evidence_lines)
        approx_tokens = current_chars // 4

        # Evidence sufficiency check:
        # If query terms have zero match with any retrieved item and classic found no match, mark insufficient
        has_evidence = len(sources) > 0 and len(formatted_context.strip()) > 30
        if has_evidence and query.strip():
            stop_words = {"the", "and", "for", "with", "that", "this", "what", "how", "why", "where", "who", "when", "does"}
            query_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())) - stop_words
            if query_words:
                has_classic_match = any("classic" in src.sources for src in sources)
                corpus_text = (formatted_context + " " + " ".join(s.title for s in sources)).lower()
                matches_any_word = any(w in corpus_text for w in query_words)
                if not has_classic_match and not matches_any_word:
                    has_evidence = False

        return ContextResult(
            formatted_context=formatted_context,
            sources=sources,
            source_map=source_map,
            total_tokens_approx=approx_tokens,
            has_sufficient_evidence=has_evidence,
        )

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        # Strip HTML tags
        no_html = re.sub(r"<[^>]+>", " ", text)
        # Normalize whitespace
        return re.sub(r"\s+", " ", no_html).strip()

    def _sanitize_for_prompt(self, text: str) -> str:
        """Neutralize malicious injection attempts like fake system tags or role impersonation."""
        if not text:
            return ""
        # Neutralize common role/instruction boundary tokens
        sanitized = re.sub(r"(?i)<\s*(system|instruction|user|assistant)\s*>", "[TAG]", text)
        sanitized = re.sub(r"(?i)<\s*/\s*(system|instruction|user|assistant)\s*>", "[/TAG]", sanitized)
        sanitized = sanitized.replace("```", "'''")
        return sanitized
