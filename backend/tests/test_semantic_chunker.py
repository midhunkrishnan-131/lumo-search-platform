"""Unit tests for document chunking service."""

from app.models.document import Document
from app.semantic.chunker import chunk_document


def test_chunking_short_document():
    doc = Document(
        id="doc-chunk-1",
        title="Short Doc",
        url="https://example.com/short",
        domain="example.com",
        main_content="This is a brief piece of text that easily fits in a single chunk.",
    )
    chunks = chunk_document(doc, chunk_size=500, chunk_overlap=50)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.document_id == "doc-chunk-1"
    assert chunk.chunk_position == 0
    assert chunk.title == "Short Doc"
    assert chunk.domain == "example.com"
    assert "brief piece of text" in chunk.chunk_text
    assert len(chunk.content_hash) == 64


def test_chunking_large_document_with_paragraphs():
    # Construct multi-paragraph text
    paras = [
        f"Paragraph {i}: Deep neural networks learn representations through backpropagation and gradient descent. Parameter updates optimize loss."
        for i in range(10)
    ]
    large_text = "\n\n".join(paras)

    doc = Document(
        id="doc-chunk-2",
        title="Neural Networks Overview",
        url="https://example.com/nn",
        domain="example.com",
        main_content=large_text,
    )

    chunks = chunk_document(doc, chunk_size=250, chunk_overlap=40)
    assert len(chunks) > 2
    for i, c in enumerate(chunks):
        assert c.chunk_position == i
        assert len(c.chunk_text) > 20
        assert c.chunk_id != ""


def test_chunking_empty_document():
    doc = Document(
        id="doc-chunk-empty",
        title="",
        url="https://example.com/empty",
        domain="example.com",
        main_content="",
        description="",
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 0
