"""Tests for Entity normalization and alias resolution."""

from app.graph.normalizer import EntityNormalizer, normalize_entity_name


def test_normalize_entity_name_cleans_case_and_punctuation():
    assert normalize_entity_name("  Python 3  ") == "python 3"
    assert normalize_entity_name('"FastAPI"') == "fastapi"
    assert normalize_entity_name("SHA-256") == "sha 256"


def test_normalizer_resolves_known_aliases_to_canonical():
    normalizer = EntityNormalizer()

    # Python aliases
    canon, etype, norm, aliases = normalizer.resolve("Python 3")
    assert canon == "Python"
    assert etype == "Technology"
    assert norm == "python"

    # RRF alias
    canon, etype, norm, _ = normalizer.resolve("RRF")
    assert canon == "Reciprocal Rank Fusion"
    assert etype == "Concept"

    # SQLite
    canon, etype, norm, _ = normalizer.resolve("sqlite3")
    assert canon == "SQLite"
    assert etype == "Technology"


def test_normalizer_prevents_unsafe_merges():
    normalizer = EntityNormalizer()

    # Different types must not merge
    assert not normalizer.should_merge("paris", "Location", "python", "Technology")

    # Distinct entities with different names must not merge
    assert not normalizer.should_merge("fastapi", "Technology", "qdrant", "Technology")

    # Known alias must merge
    assert normalizer.should_merge("python 3", "Technology", "python", "Technology")
