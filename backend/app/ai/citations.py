"""Citation parser, validator, and source resolver for LUMO AI Search."""

from __future__ import annotations

import re
from typing import Any

from app.ai.context import ContextSource
from app.schemas.ai import CitationItem, SourceItem


class CitationValidator:
    """Validates citations in AI-generated answers against actual retrieved sources."""

    def __init__(self, source_map: dict[str, ContextSource]) -> None:
        self.source_map = source_map

    def validate_and_extract(self, answer_text: str) -> tuple[str, list[CitationItem], list[SourceItem]]:
        """Scan answer text for citation tokens [S1], validate them, strip invalid citations, and return structured metadata.

        Args:
            answer_text: Raw answer string from the AI provider.

        Returns:
            Tuple of:
            - Cleaned answer text with invalid citations stripped
            - List of verified CitationItem objects
            - List of all available SourceItem objects
        """
        if not answer_text:
            return "", [], self._all_sources()

        # Find all citation tokens like [S1], [S2], [S1, S2], [S1][S2]
        # Pattern matches [S\d+]
        found_tokens = re.findall(r"\[S(\d+)\]", answer_text)
        unique_cites = sorted(list(set(int(t) for t in found_tokens)))

        valid_citations: list[CitationItem] = []
        invalid_tokens: set[str] = set()

        for num in unique_cites:
            key = f"S{num}"
            if key in self.source_map:
                src = self.source_map[key]
                valid_citations.append(
                    CitationItem(
                        citation_id=f"[{key}]",
                        source_id=key,
                        document_id=src.document_id,
                        title=src.title,
                        url=src.url,
                        domain=src.domain,
                        snippet=src.snippet or src.content[:200],
                    )
                )
            else:
                invalid_tokens.add(f"[S{num}]")

        # Strip hallucinated/invalid citations from answer text
        cleaned_text = answer_text
        for invalid_token in invalid_tokens:
            cleaned_text = cleaned_text.replace(invalid_token, "")

        # Clean up any resulting double spaces
        cleaned_text = re.sub(r" {2,}", " ", cleaned_text).strip()

        all_sources = self._all_sources()

        return cleaned_text, valid_citations, all_sources

    def _all_sources(self) -> list[SourceItem]:
        sources: list[SourceItem] = []
        for src in self.source_map.values():
            sources.append(
                SourceItem(
                    source_id=src.source_id,
                    document_id=src.document_id,
                    title=src.title,
                    url=src.url,
                    domain=src.domain,
                    snippet=src.snippet,
                    score=src.retrieval_score,
                    retrieval_sources=src.sources,
                )
            )
        return sources
