"""Tests for HTML structured content extractor."""

from app.processor.extractor import (
    extract_canonical_url,
    extract_document_data,
    extract_headings,
    extract_language,
    normalize_text,
)


def test_normalize_text():
    raw = "   Line 1 with   lots of    spaces.  \r\n\r\n\r\n\r\n  Line 2.   \n\n\n\n  Line 3.  "
    normalized = normalize_text(raw)
    assert normalized == "Line 1 with lots of spaces.\n\nLine 2.\n\nLine 3."


def test_extract_metadata_and_headings():
    html = """
    <!DOCTYPE html>
    <html lang="en-US">
    <head>
        <title>Article Title - Brand Name</title>
        <meta name="description" content="This is an informative meta description.">
        <meta name="author" content="Jane Doe">
        <meta property="article:published_time" content="2026-05-15T08:00:00Z">
        <meta property="article:modified_time" content="2026-05-16T10:30:00Z">
        <link rel="canonical" href="https://example.com/posts/article-one">
    </head>
    <body>
        <article>
            <h1>Main Title</h1>
            <p>First paragraph of the main article with valuable knowledge.</p>
            <h2>Subheading 1</h2>
            <p>Second paragraph providing in-depth analysis of the topic.</p>
            <h3>Detail A</h3>
            <p>Third paragraph detailing technical nuances.</p>
        </article>
    </body>
    </html>
    """
    data = extract_document_data(html, url="https://example.com/posts/article-one")

    assert data.extraction_status == "completed"
    assert data.title == "Article Title - Brand Name"
    assert data.description == "This is an informative meta description."
    assert data.author == "Jane Doe"
    assert data.published_date == "2026-05-15T08:00:00Z"
    assert data.modified_date == "2026-05-16T10:30:00Z"
    assert data.canonical_url == "https://example.com/posts/article-one"
    assert data.language == "en-US"
    assert len(data.headings) == 3
    assert data.headings[0] == {"tag": "h1", "level": 1, "text": "Main Title"}
    assert data.headings[1] == {"tag": "h2", "level": 2, "text": "Subheading 1"}
    assert data.headings[2] == {"tag": "h3", "level": 3, "text": "Detail A"}
    assert "First paragraph of the main article" in data.main_content
    assert data.word_count > 10
    assert len(data.content_hash) == 64


def test_canonical_url_ssrf_rejection():
    # Canonical pointing to localhost or private IP must be rejected (returns None)
    html = """
    <html>
    <head>
        <link rel="canonical" href="http://127.0.0.1:8000/internal-secret">
    </head>
    <body>
        <p>Some content</p>
    </body>
    </html>
    """
    data = extract_document_data(html, url="https://example.com/page")
    assert data.canonical_url is None


def test_canonical_relative_url_resolution():
    html = """
    <html>
    <head>
        <link rel="canonical" href="/canonical/page">
    </head>
    <body>
        <p>Some content</p>
    </body>
    </html>
    """
    data = extract_document_data(html, url="https://example.com/sub/dir/page")
    assert data.canonical_url == "https://example.com/canonical/page"
