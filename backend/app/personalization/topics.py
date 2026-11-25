"""Topic normalization, extraction, and non-sensitive signal classification."""

from __future__ import annotations

import re

from app.graph.extractor import EntityExtractor
from app.graph.normalizer import normalize_entity_name

# Guardrail: never infer or store sensitive personal attributes as topics
_SENSITIVE_TOPIC_BLOCKLIST = {
    "religion",
    "religious",
    "christianity",
    "islam",
    "judaism",
    "hinduism",
    "buddhism",
    "atheism",
    "politics",
    "political",
    "democrat",
    "republican",
    "liberal",
    "conservative",
    "sexual orientation",
    "gender identity",
    "lgbtq",
    "medical",
    "health condition",
    "mental health",
    "diagnosis",
    "illness",
    "disease",
    "disability",
    "ethnicity",
    "ethnic",
    "race",
}


def normalize_topic(raw: str) -> str:
    """Normalize topic string for deduplication and indexing."""
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    return normalize_entity_name(cleaned)[:160]


def is_sensitive_topic(raw: str) -> bool:
    """Return True if topic matches sensitive personal trait categories that must not be profiled."""
    norm = normalize_topic(raw)
    if not norm:
        return True
    return any(term in norm for term in _SENSITIVE_TOPIC_BLOCKLIST)


def extract_safe_topics(text: str, max_topics: int = 5) -> list[str]:
    """Extract non-sensitive knowledge/technical topics from text reusing Graph EntityExtractor."""
    if not text or not text.strip():
        return []
    extractor = EntityExtractor()
    entities = extractor.extract(text, max_entities=max_topics * 2)
    topics: list[str] = []
    seen: set[str] = set()
    for ent in entities:
        norm = normalize_topic(ent.name)
        if norm and norm not in seen and not is_sensitive_topic(ent.name):
            seen.add(norm)
            topics.append(ent.name)
            if len(topics) >= max_topics:
                break
    return topics
