"""Unit tests for HTML link extraction and title parsing."""

from app.crawler.extractor import extract_links_from_html


def test_extract_links_and_title():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Example Page Title</title>
    </head>
    <body>
        <h1>Heading</h1>
        <a href="/about">About Us</a>
        <a href="https://example.com/docs">Documentation</a>
        <a href="contact.html">Contact</a>
        <a href="#section">Jump</a>
        <a href="javascript:void(0)">Do Not Crawl</a>
        <a href="mailto:info@example.com">Email Us</a>
        <a href="/about">Duplicate About</a>
    </body>
    </html>
    """
    extracted = extract_links_from_html(html, "https://example.com/index.html")

    assert extracted.title == "Example Page Title"
    assert "https://example.com/about" in extracted.links
    assert "https://example.com/docs" in extracted.links
    assert "https://example.com/contact.html" in extracted.links

    # Non-web and fragment links must be excluded
    for link in extracted.links:
        assert not link.startswith("javascript:")
        assert not link.startswith("mailto:")
        assert not link.startswith("#")

    # Deduplicated
    assert len(extracted.links) == 3


def test_extract_links_empty_or_malformed():
    assert extract_links_from_html("", "https://example.com").links == []
    assert extract_links_from_html("<p>No links here</p>", "https://example.com").links == []
