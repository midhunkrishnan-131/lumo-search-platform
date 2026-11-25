"""Tests for Entity and Relationship extraction and grounding in LUMO Knowledge Graph."""

import pytest

from app.graph.extractor import EntityExtractor, ExtractedEntity
from app.graph.normalizer import EntityNormalizer
from app.graph.relationships import RelationshipExtractor


def test_entity_extractor_finds_known_entities_and_technologies():
    extractor = EntityExtractor()
    text = (
        "FastAPI is a modern Python web framework for building APIs. "
        "It integrates seamlessly with Qdrant for semantic search and PostgreSQL for data storage."
    )
    entities = extractor.extract(text, title="FastAPI and Python Architecture")
    names = {e.name for e in entities}

    assert "FastAPI" in names
    assert "Python" in names
    assert "Qdrant" in names
    assert "PostgreSQL" in names

    # Verify types
    type_map = {e.name: e.entity_type for e in entities}
    assert type_map["FastAPI"] == "Technology"
    assert type_map["Python"] == "Technology"
    assert type_map["Qdrant"] == "Technology"


def test_entity_extractor_structural_patterns():
    extractor = EntityExtractor()
    text = (
        "Guido van Rossum released Python in 1991. "
        "OpenAI Inc developed large language models. "
        "The company is headquartered in San Francisco."
    )
    entities = extractor.extract(text)
    names = {e.name for e in entities}

    assert any("OpenAI" in n for n in names)
    assert any("San Francisco" in n for n in names)


def test_relationship_extractor_detects_syntactic_patterns():
    extractor = EntityExtractor()
    rel_extractor = RelationshipExtractor()

    text = (
        "LUMO uses Hybrid Search combining BM25 and Semantic Retrieval. "
        "FastAPI was developed by Sebastián Ramírez."
    )
    entities = extractor.extract(text)
    relationships = rel_extractor.extract(text, entities)

    rel_types = {r.relationship_type for r in relationships}
    assert len(relationships) > 0
    # Every relationship must have non-empty grounded sentence snippet evidence
    for rel in relationships:
        assert len(rel.snippet) > 10
        assert rel.snippet in text or any(word in text for word in rel.snippet.split()[:3])


def test_relationship_extractor_no_false_links_without_co_occurrence():
    extractor = EntityExtractor()
    rel_extractor = RelationshipExtractor()

    # Entities mentioned in completely isolated, separate sentences
    text = (
        "Python is an interpreted programming language. "
        "In a completely unrelated topic, Paris is the capital of France."
    )
    entities = [
        ExtractedEntity(name="Python", entity_type="Technology", normalized_name="python"),
        ExtractedEntity(name="Paris", entity_type="Location", normalized_name="paris"),
    ]
    relationships = rel_extractor.extract(text, entities)
    assert len(relationships) == 0


def test_ai_extraction_strictly_enforces_text_grounding():
    extractor = EntityExtractor()
    text = "FastAPI is a Python web framework."

    class MockAIResponse:
        def __init__(self, content):
            self.content = content

    class MockAIRouter:
        def execute(self, prompt, timeout_seconds=12):
            # Model returns one grounded entity and one hallucinated/invented entity
            content = '[{"name": "FastAPI", "type": "Technology", "snippet": "FastAPI is a Python web framework."}, {"name": "HallucinatedQuantumDB", "type": "Technology", "snippet": "does not exist in text"}]'
            return MockAIResponse(content), False, "mock"

    entities = extractor.extract_with_ai(text, MockAIRouter())
    names = {e.name for e in entities}
    assert "FastAPI" in names
    # Hallucinated entity must be discarded because it does not appear in text
    assert "HallucinatedQuantumDB" not in names
