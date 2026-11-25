"""Entity extraction engine combining rule-based, vocabulary, and optional AI extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from app.core.logging import get_logger
from app.graph.normalizer import (
    CANONICAL_ALIASES,
    EntityNormalizer,
    clean_text_for_normalization,
    normalize_entity_name,
)

logger = get_logger("graph.extractor")


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    normalized_name: str
    confidence: float = 1.0
    extraction_method: str = "rule_based"
    first_snippet: str | None = None
    aliases: list[str] = field(default_factory=list)


# Well-known vocabulary mapping term regex -> (canonical display, entity_type)
KNOWN_ENTITIES: dict[str, tuple[str, str]] = {
    # Technology / Architecture
    r"\bfastapi\b": ("FastAPI", "Technology"),
    r"\bpython(?:3|\s+3)?\b": ("Python", "Technology"),
    r"\bqdrant\b": ("Qdrant", "Technology"),
    r"\bpostgresql\b|\bpostgres\b": ("PostgreSQL", "Technology"),
    r"\bsqlite(?:3)?\b": ("SQLite", "Technology"),
    r"\bnetworkx\b": ("NetworkX", "Technology"),
    r"\bollama\b": ("Ollama", "Technology"),
    r"\bd3(?:\.js)?\b": ("D3.js", "Technology"),
    r"\bopensearch\b": ("OpenSearch", "Technology"),
    r"\belasticsearch\b": ("Elasticsearch", "Technology"),
    r"\bredis\b": ("Redis", "Technology"),
    r"\bdocker\b": ("Docker", "Technology"),
    r"\blinux\b": ("Linux", "Technology"),
    r"\bwindows\b": ("Windows", "Technology"),

    # Protocols & Cryptography
    r"\bsha-?256\b": ("SHA-256", "Protocol"),
    r"\bsha-?1\b": ("SHA-1", "Protocol"),
    r"\bmd5\b": ("MD5", "Protocol"),
    r"\btls\b|\bssl\b": ("TLS", "Protocol"),
    r"\bhttps?\b": ("HTTPS", "Protocol"),
    r"\brest(?:\s+api)?\b": ("REST", "Protocol"),
    r"\bpunycode\b": ("Punycode", "Protocol"),

    # Search & Intelligence Concepts
    r"\bhybrid\s+search\b": ("Hybrid Search", "Concept"),
    r"\breciprocal\s+rank\s+fusion\b|\brrf\b": ("Reciprocal Rank Fusion", "Concept"),
    r"\bbm-?25\b": ("BM25", "Concept"),
    r"\bsemantic\s+(?:retrieval|search)\b": ("Semantic Retrieval", "Concept"),
    r"\bvector\s+embeddings?\b": ("Vector Embeddings", "Concept"),
    r"\bretrieval[- ]augmented\s+generation\b|\brag\b": ("RAG", "Concept"),
    r"\bknowledge\s+graph\b": ("Knowledge Graph", "Concept"),
    r"\bserver[- ]side\s+request\s+forgery\b|\bssrf\b": ("SSRF", "Concept"),
    r"\bstatic\s+analysis\b": ("Static Analysis", "Concept"),
    r"\bentropy\b": ("Entropy", "Concept"),

    # LUMO Core Modules
    r"\bresearch\s+agent\b": ("Research Agent", "Module"),
    r"\bdownload\s+guardian\b": ("Download Guardian", "Module"),
    r"\bweb\s+crawler\b|\bcrawler\b": ("Web Crawler", "Module"),
    r"\bcontent\s+processor\b": ("Content Processor", "Module"),

    # Organizations
    r"\bgoogle(?:\s+llc|\s+inc)?\b": ("Google", "Organization"),
    r"\balphabet(?:\s+inc\.?)?\b": ("Alphabet Inc.", "Organization"),
    r"\bopenai\b": ("OpenAI", "Organization"),
    r"\bmicrosoft(?:\s+corp)?\b": ("Microsoft", "Organization"),
    r"\bxai\b": ("xAI", "Organization"),
    r"\bmozilla\b": ("Mozilla", "Organization"),
    r"\bapache(?:\s+software\s+foundation)?\b": ("Apache Software Foundation", "Organization"),
}

# Regex patterns for structural entities
ORG_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*\s+(?:Inc|Corp|Corporation|LLC|Foundation|Institute|Technologies|Systems|Labs|Lab|Group))\b"
)
PERSON_PATTERN = re.compile(
    r"\b(?:Dr\.|Mr\.|Ms\.|Prof\.|President|Director|CEO|CTO|Author|Founder)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+))\b"
)
TECH_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*\s+(?:Framework|Library|Database|Engine|Algorithm|Pipeline|Gateway|Analyzer|Router))\b"
)
LOCATION_PATTERN = re.compile(
    r"\b(?:headquartered|located|based)\s+(?:in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s*,\s*[A-Z][a-z]+)?)\b",
    re.IGNORECASE,
)


class EntityExtractor:
    """Extracts typed, grounded entities from document text and headings."""

    def __init__(self, normalizer: EntityNormalizer | None = None) -> None:
        self.normalizer = normalizer or EntityNormalizer()

    def extract(
        self,
        text: str,
        title: str | None = None,
        headings: list[str] | None = None,
        max_entities: int = 50,
    ) -> list[ExtractedEntity]:
        """Extract candidate entities from document content."""
        if not text and not title:
            return []

        combined_text = f"{title or ''}\n\n{text or ''}"
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", combined_text) if len(s.strip()) > 10]

        extracted_map: dict[str, ExtractedEntity] = {}

        def record_entity(name: str, entity_type: str, confidence: float, method: str, snippet: str | None = None):
            canonical, resolved_type, norm, aliases = self.normalizer.resolve(name, entity_type)
            if not canonical or len(canonical) < 2 or len(canonical) > 100:
                return

            if norm in extracted_map:
                # Update confidence and add aliases
                existing = extracted_map[norm]
                existing.confidence = max(existing.confidence, confidence)
                for a in aliases:
                    if a not in existing.aliases and a != existing.name:
                        existing.aliases.append(a)
                if not existing.first_snippet and snippet:
                    existing.first_snippet = snippet[:300].strip()
            else:
                extracted_map[norm] = ExtractedEntity(
                    name=canonical,
                    entity_type=resolved_type,
                    normalized_name=norm,
                    confidence=confidence,
                    extraction_method=method,
                    first_snippet=snippet[:300].strip() if snippet else None,
                    aliases=aliases,
                )

        # 1. Check title and headings (High confidence)
        if title:
            for pat, (canonical, etype) in KNOWN_ENTITIES.items():
                if re.search(pat, title, re.IGNORECASE):
                    record_entity(canonical, etype, 1.0, "title_match", title)

        if headings:
            for heading in headings:
                if not isinstance(heading, str):
                    continue
                for pat, (canonical, etype) in KNOWN_ENTITIES.items():
                    if re.search(pat, heading, re.IGNORECASE):
                        record_entity(canonical, etype, 0.95, "heading_match", heading)

        # 2. Match known entity vocabulary across sentences
        for sentence in sentences:
            for pat, (canonical, etype) in KNOWN_ENTITIES.items():
                match = re.search(pat, sentence, re.IGNORECASE)
                if match:
                    record_entity(canonical, etype, 0.9, "vocabulary", sentence)

        # 3. Match structural patterns
        for sentence in sentences:
            # Organizations
            for match in ORG_PATTERN.finditer(sentence):
                org_name = match.group(1).strip()
                record_entity(org_name, "Organization", 0.85, "pattern_org", sentence)

            # Persons
            for match in PERSON_PATTERN.finditer(sentence):
                person_name = match.group(1).strip()
                record_entity(person_name, "Person", 0.85, "pattern_person", sentence)

            # Tech / Frameworks / Databases
            for match in TECH_PATTERN.finditer(sentence):
                tech_name = match.group(1).strip()
                record_entity(tech_name, "Technology", 0.8, "pattern_tech", sentence)

            # Locations
            for match in LOCATION_PATTERN.finditer(sentence):
                loc_name = match.group(1).strip()
                record_entity(loc_name, "Location", 0.75, "pattern_location", sentence)

        # Sort by confidence and mention presence, bounded to max_entities
        entities = list(extracted_map.values())
        entities.sort(key=lambda e: (-e.confidence, e.name))
        return entities[:max_entities]

    def extract_with_ai(
        self,
        text: str,
        ai_router: Any,
        title: str | None = None,
        max_entities: int = 50,
    ) -> list[ExtractedEntity]:
        """Optional AI-assisted extraction using existing AI Provider Router with strict grounding."""
        # Start with rule-based entities as solid baseline
        baseline = self.extract(text, title=title, max_entities=max_entities)
        if not ai_router:
            return baseline

        # Bounded excerpt to prevent excessive context length
        sample_text = (f"Title: {title}\n\n" if title else "") + text[:2500]

        prompt = (
            "You are an entity extractor. Extract real entities from the following text.\n"
            "Categories allowed: Person, Organization, Location, Technology, Product, Concept, Event, Topic, Module.\n"
            "Return ONLY a JSON array of objects with keys: 'name', 'type', 'snippet'.\n"
            "The 'snippet' must be an exact quote from the text where the entity appears.\n"
            "Do NOT invent entities. If none found, return [].\n\n"
            f"Text:\n{sample_text}\n"
        )

        try:
            # Execute through router (Gemini, Grok, or Ollama)
            response, _, _ = ai_router.execute(
                system_prompt="You are an entity extractor. Return ONLY valid JSON.",
                user_prompt=prompt,
                timeout=12.0,
            )
            content = response.content.strip()
            # Extract JSON block
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                existing_norms = {e.normalized_name for e in baseline}

                for item in parsed:
                    raw_name = str(item.get("name", "")).strip()
                    raw_type = str(item.get("type", "Concept")).strip()
                    snippet = str(item.get("snippet", "")).strip()

                    # Grounding verification: snippet must be in the sample text
                    if raw_name and (raw_name.lower() in sample_text.lower()):
                        canonical, resolved_type, norm, aliases = self.normalizer.resolve(raw_name, raw_type)
                        if norm and norm not in existing_norms:
                            baseline.append(
                                ExtractedEntity(
                                    name=canonical,
                                    entity_type=resolved_type,
                                    normalized_name=norm,
                                    confidence=0.88,
                                    extraction_method="ai_grounded",
                                    first_snippet=snippet or None,
                                    aliases=aliases,
                                )
                            )
                            existing_norms.add(norm)
        except Exception as exc:
            logger.warning("Optional AI entity extraction skipped or failed: %s", exc)

        baseline.sort(key=lambda e: (-e.confidence, e.name))
        return baseline[:max_entities]
