"""Entity normalization and alias resolution for LUMO Knowledge Graph."""

from __future__ import annotations

import re
import unicodedata

CANONICAL_ALIASES: dict[str, tuple[str, str]] = {
    # Technology / Protocols
    "python": ("Python", "Technology"),
    "python 3": ("Python", "Technology"),
    "python3": ("Python", "Technology"),
    "python programming language": ("Python", "Technology"),
    "fastapi": ("FastAPI", "Technology"),
    "fastapi gateway": ("FastAPI", "Technology"),
    "fastapi framework": ("FastAPI", "Technology"),
    "qdrant": ("Qdrant", "Technology"),
    "qdrant vector db": ("Qdrant", "Technology"),
    "qdrant vector database": ("Qdrant", "Technology"),
    "postgresql": ("PostgreSQL", "Technology"),
    "postgres": ("PostgreSQL", "Technology"),
    "sqlite": ("SQLite", "Technology"),
    "sqlite3": ("SQLite", "Technology"),
    "networkx": ("NetworkX", "Technology"),
    "ollama": ("Ollama", "Technology"),
    "d3": ("D3.js", "Technology"),
    "d3.js": ("D3.js", "Technology"),
    "d3js": ("D3.js", "Technology"),
    "sha-256": ("SHA-256", "Protocol"),
    "sha256": ("SHA-256", "Protocol"),
    "sha-1": ("SHA-1", "Protocol"),
    "sha1": ("SHA-1", "Protocol"),
    "md5": ("MD5", "Protocol"),
    "tls": ("TLS", "Protocol"),
    "ssl": ("TLS", "Protocol"),
    "https": ("HTTPS", "Protocol"),
    "http": ("HTTP", "Protocol"),
    "rest": ("REST", "Protocol"),
    "rest api": ("REST", "Protocol"),

    # Concepts
    "hybrid search": ("Hybrid Search", "Concept"),
    "reciprocal rank fusion": ("Reciprocal Rank Fusion", "Concept"),
    "rrf": ("Reciprocal Rank Fusion", "Concept"),
    "bm25": ("BM25", "Concept"),
    "bm-25": ("BM25", "Concept"),
    "dense retrieval": ("Dense Retrieval", "Concept"),
    "semantic retrieval": ("Semantic Retrieval", "Concept"),
    "semantic search": ("Semantic Search", "Concept"),
    "vector embeddings": ("Vector Embeddings", "Concept"),
    "vector embedding": ("Vector Embeddings", "Concept"),
    "retrieval augmented generation": ("RAG", "Concept"),
    "retrieval-augmented generation": ("RAG", "Concept"),
    "rag": ("RAG", "Concept"),
    "server-side request forgery": ("SSRF", "Concept"),
    "ssrf": ("SSRF", "Concept"),
    "knowledge graph": ("Knowledge Graph", "Concept"),
    "static analysis": ("Static Analysis", "Concept"),

    # Modules
    "research agent": ("Research Agent", "Module"),
    "download guardian": ("Download Guardian", "Module"),
    "crawler": ("Web Crawler", "Module"),
    "content processor": ("Content Processor", "Module"),

    # Organizations
    "google": ("Google", "Organization"),
    "google llc": ("Google", "Organization"),
    "google inc": ("Google", "Organization"),
    "alphabet": ("Alphabet Inc.", "Organization"),
    "alphabet inc": ("Alphabet Inc.", "Organization"),
    "openai": ("OpenAI", "Organization"),
    "microsoft": ("Microsoft", "Organization"),
    "microsoft corp": ("Microsoft", "Organization"),
    "xai": ("xAI", "Organization"),
    "mozilla": ("Mozilla", "Organization"),
    "apache software foundation": ("Apache Software Foundation", "Organization"),
    "apache": ("Apache Software Foundation", "Organization"),
}


def clean_text_for_normalization(text: str) -> str:
    """Normalize unicode, whitespace, and strip common surrounding punctuation."""
    if not text:
        return ""
    # Normalize unicode to NFKC
    normalized = unicodedata.normalize("NFKC", text)
    # Replace non-breaking spaces and irregular whitespace
    normalized = re.sub(r"[\s\u200b\u200c\u200d\u200e\u200f]+", " ", normalized)
    # Strip quotes, brackets, and leading/trailing punctuation
    cleaned = normalized.strip().strip("'\"`’“”«»()[]{}.,;:!?-_")
    return cleaned


def normalize_entity_name(name: str) -> str:
    """Produce a deterministic, lowercase search and deduplication key."""
    cleaned = clean_text_for_normalization(name)
    lowered = cleaned.lower()
    # Normalize internal punctuation and dashes
    lowered = re.sub(r"[\-_]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


class EntityNormalizer:
    """Normalizes candidate entity mentions, resolves known aliases, and maps to canonical entities."""

    def __init__(self, custom_aliases: dict[str, tuple[str, str]] | None = None) -> None:
        self.alias_table: dict[str, tuple[str, str]] = dict(CANONICAL_ALIASES)
        if custom_aliases:
            self.alias_table.update(custom_aliases)

    def register_alias(self, alias: str, canonical_name: str, entity_type: str) -> None:
        """Register a new alias mapping."""
        norm = normalize_entity_name(alias)
        if norm:
            self.alias_table[norm] = (canonical_name.strip(), entity_type.strip())

    def resolve(
        self,
        name: str,
        inferred_type: str = "Concept",
    ) -> tuple[str, str, str, list[str]]:
        """Resolve a raw entity mention into canonical (canonical_name, entity_type, normalized_name, aliases).

        Returns:
            canonical_name: Capitalized/canonical display name.
            entity_type: Canonical category (e.g., Technology, Concept, Organization, etc.).
            normalized_name: Lowercased indexing key.
            aliases: Discovered or known alternate representations.
        """
        cleaned = clean_text_for_normalization(name)
        if not cleaned:
            return "", inferred_type, "", []

        norm = normalize_entity_name(cleaned)
        aliases: list[str] = []

        if norm in self.alias_table:
            canonical_name, entity_type = self.alias_table[norm]
            canonical_norm = normalize_entity_name(canonical_name)
            if cleaned != canonical_name:
                aliases.append(cleaned)
            return canonical_name, entity_type, canonical_norm, aliases

        # Generic formatting: title-case if entirely lowercase, preserve camelCase/acronyms
        canonical_name = cleaned
        if cleaned.islower():
            canonical_name = cleaned.title()

        return canonical_name, inferred_type, norm, aliases

    def should_merge(
        self,
        entity_a_norm: str,
        entity_a_type: str,
        entity_b_norm: str,
        entity_b_type: str,
    ) -> bool:
        """Conservative safety check to prevent erroneous merging of distinct entities."""
        if entity_a_type != entity_b_type and entity_a_type != "Concept" and entity_b_type != "Concept":
            return False

        if entity_a_norm == entity_b_norm:
            return True

        # Check if one is a registered alias of the other
        if entity_a_norm in self.alias_table:
            target_name, _ = self.alias_table[entity_a_norm]
            if normalize_entity_name(target_name) == entity_b_norm:
                return True

        if entity_b_norm in self.alias_table:
            target_name, _ = self.alias_table[entity_b_norm]
            if normalize_entity_name(target_name) == entity_a_norm:
                return True

        return False
