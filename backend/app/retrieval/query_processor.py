"""Deterministic Intelligent Query Processing for LUMO Phase 29."""

from __future__ import annotations

import re
from typing import Any

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "what",
    "when", "where", "which", "who", "why", "with",
}

_EXPANSIONS = {
    "db": ["database"],
    "ml": ["machine learning"],
    "ai": ["artificial intelligence"],
    "rag": ["retrieval augmented generation"],
    "api": ["endpoint", "rest"],
    "kg": ["knowledge graph"],
}


def process_query(query: str) -> dict[str, Any]:
    """Normalize, classify, extract key terms, decompose multi-part queries, and preserve original."""
    original = (query or "").strip()
    normalized = " ".join(original.split())
    low = normalized.lower()

    # Deterministic intent classification
    if any(k in low for k in ("my notes", "knowledge hub", "saved", "collection")):
        intent = "knowledge_hub"
    elif " and " in low and ("?" in original or len(normalized.split()) > 6):
        intent = "multi_part"
    elif any(k in low for k in ("research", "investigate", "compare", "overview")):
        intent = "research"
    elif original.endswith("?") or any(low.startswith(p) for p in ("what ", "why ", "how ", "explain ")):
        intent = "natural_language"
    else:
        intent = "keyword"

    tokens = re.findall(r"[A-Za-z0-9_.-]+", low)
    terms = [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]

    expanded: list[str] = []
    for t in terms:
        for syn in _EXPANSIONS.get(t, []):
            if syn not in expanded:
                expanded.append(syn)

    # Multi-part decomposition (bounded to 3 sub-queries)
    sub_queries: list[str] = [normalized] if normalized else []
    if intent in ("multi_part", "research") and (" and " in low or ";" in normalized):
        parts = [p.strip() for p in re.split(r"\band\b|;", normalized, flags=re.IGNORECASE) if len(p.strip()) >= 3]
        if len(parts) > 1:
            sub_queries = parts[:3]

    return {
        "original_query": original,
        "normalized_query": normalized,
        "intent": intent,
        "terms": terms[:20],
        "expanded_terms": expanded[:10],
        "sub_queries": sub_queries,
    }
