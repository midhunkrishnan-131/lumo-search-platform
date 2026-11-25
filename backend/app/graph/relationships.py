"""Relationship extraction engine detecting grounded entity connections from source sentences."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.logging import get_logger
from app.graph.extractor import ExtractedEntity

logger = get_logger("graph.relationships")


@dataclass
class ExtractedRelationship:
    source_name: str
    source_type: str
    target_name: str
    target_type: str
    relationship_type: str
    confidence: float
    extraction_method: str
    snippet: str


# Predicate regex patterns mapping relation -> compiled regex
RELATION_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "DEVELOPED",
        re.compile(r"\b(?:developed\s+by|created\s+by|authored\s+by|designed\s+by|built\s+by|released\s+by)\b", re.IGNORECASE),
        0.95,
    ),
    (
        "FOUNDED",
        re.compile(r"\b(?:founded\s+by|co[- ]founded\s+by|established\s+by)\b", re.IGNORECASE),
        0.95,
    ),
    (
        "WORKS_FOR",
        re.compile(r"\b(?:works\s+(?:for|at)|engineer\s+at|researcher\s+at|ceo\s+of|cto\s+of|director\s+at)\b", re.IGNORECASE),
        0.9,
    ),
    (
        "LOCATED_IN",
        re.compile(r"\b(?:located\s+in|headquartered\s+in|based\s+in)\b", re.IGNORECASE),
        0.9,
    ),
    (
        "PART_OF",
        re.compile(r"\b(?:part\s+of|component\s+of|module\s+(?:in|of)|subsystem\s+of|feature\s+of)\b", re.IGNORECASE),
        0.88,
    ),
    (
        "USES",
        re.compile(r"\b(?:uses|utilizes|implements|relies\s+on|built\s+with|powered\s+by|integrates\s+with)\b", re.IGNORECASE),
        0.85,
    ),
    (
        "OWNS",
        re.compile(r"\b(?:owns|acquired|parent\s+company\s+of|subsidiary\s+of)\b", re.IGNORECASE),
        0.85,
    ),
    (
        "COLLABORATES_WITH",
        re.compile(r"\b(?:collaborates\s+with|partnered\s+with|works\s+alongside)\b", re.IGNORECASE),
        0.8,
    ),
    (
        "HAS_TOPIC",
        re.compile(r"\b(?:focuses\s+on|covers\s+topic|discusses|explains|analyzes)\b", re.IGNORECASE),
        0.75,
    ),
]


class RelationshipExtractor:
    """Extracts typed, grounded relationships between entities mentioned in the same text snippet."""

    def extract(
        self,
        text: str,
        entities: list[ExtractedEntity],
        max_relationships: int = 100,
    ) -> list[ExtractedRelationship]:
        """Extract relationships supported by sentence-level evidence."""
        if not text or len(entities) < 2:
            return []

        # Split into sentences for strict grounding
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if len(s.strip()) > 15
        ]

        relationships: list[ExtractedRelationship] = []
        seen_pairs: set[tuple[str, str, str]] = set()

        for sentence in sentences:
            # Find which entities occur in this specific sentence
            present_entities: list[ExtractedEntity] = []
            for ent in entities:
                # Check entity name or aliases
                names_to_check = [ent.name] + ent.aliases
                for n in names_to_check:
                    if re.search(rf"\b{re.escape(n)}\b", sentence, re.IGNORECASE):
                        present_entities.append(ent)
                        break

            if len(present_entities) < 2:
                continue

            # Check entity pairs in this sentence
            for i in range(len(present_entities)):
                for j in range(i + 1, len(present_entities)):
                    e1 = present_entities[i]
                    e2 = present_entities[j]

                    if e1.normalized_name == e2.normalized_name:
                        continue

                    # Search text between the two entity mentions
                    m1 = re.search(rf"\b{re.escape(e1.name)}\b", sentence, re.IGNORECASE)
                    m2 = re.search(rf"\b{re.escape(e2.name)}\b", sentence, re.IGNORECASE)

                    assigned_rel = "RELATED_TO"
                    rel_conf = 0.70
                    extraction_method = "co_occurrence"
                    src, tgt = e1, e2

                    if m1 and m2:
                        start_pos = min(m1.end(), m2.end())
                        end_pos = max(m1.start(), m2.start())
                        between_text = sentence[start_pos:end_pos] if start_pos < end_pos else sentence

                        # Check typed relation patterns
                        for rel_type, pattern, base_conf in RELATION_PATTERNS:
                            if pattern.search(between_text) or pattern.search(sentence):
                                assigned_rel = rel_type
                                rel_conf = base_conf
                                extraction_method = "syntactic_pattern"

                                # Adjust direction for passive voice (e.g. "X was developed by Y" -> Y DEVELOPED X)
                                if rel_type in ("DEVELOPED", "FOUNDED") and m1.start() < m2.start():
                                    src, tgt = e2, e1
                                break

                    pair_key = (src.normalized_name, tgt.normalized_name, assigned_rel)
                    rev_key = (tgt.normalized_name, src.normalized_name, assigned_rel)

                    if pair_key not in seen_pairs and rev_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        relationships.append(
                            ExtractedRelationship(
                                source_name=src.name,
                                source_type=src.entity_type,
                                target_name=tgt.name,
                                target_type=tgt.entity_type,
                                relationship_type=assigned_rel,
                                confidence=rel_conf,
                                extraction_method=extraction_method,
                                snippet=sentence[:350].strip(),
                            )
                        )

                        if len(relationships) >= max_relationships:
                            return relationships

        return relationships
