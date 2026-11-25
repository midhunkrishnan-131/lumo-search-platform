"""Unit tests for embedding service and normalization."""

import math
from app.semantic.embedding import LocalEmbeddingService


def test_embedding_dimension_and_normalization():
    svc = LocalEmbeddingService(dimension=384)
    vec = svc.embed_query("quantum computing architecture")
    assert len(vec) == 384

    # Check L2 norm is approximately 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-4


def test_embedding_batch():
    svc = LocalEmbeddingService(dimension=384, batch_size=4)
    texts = [
        "First document text about search engines.",
        "Second document describing vector databases.",
        "Third document discussing deep learning.",
    ]
    vectors = svc.embed_texts(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 384


def test_embedding_empty_text():
    svc = LocalEmbeddingService(dimension=384)
    vec = svc.embed_query("")
    assert len(vec) == 384
    assert sum(vec) == 0.0


def test_embedding_status():
    svc = LocalEmbeddingService(dimension=384)
    status = svc.get_status()
    assert status["dimension"] == 384
    assert status["model_name"] == "all-MiniLM-L6-v2"
    assert status["backend"] != "uninitialized"
