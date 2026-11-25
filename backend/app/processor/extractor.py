"""HTML structured content extractor and text normalizer for LUMO Phase 4."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.crawler.validator import validate_and_screen_url
from app.processor.cleaner import clean_html_soup


@dataclass
class ExtractedDocumentData:
    url: str
    canonical_url: str | None
    title: str | None
    description: str | None
    main_content: str
    headings: list[dict[str, str | int]] = field(default_factory=list)
    language: str | None = None
    author: str | None = None
    published_date: str | None = None
    modified_date: str | None = None
    content_hash: str = ""
    word_count: int = 0
    extraction_status: str = "completed"
    error_message: str | None = None


def normalize_text(text: str) -> str:
    """Normalize text by trimming lines, standardizing line breaks, and preserving paragraphs."""
    if not text:
        return ""

    # Replace carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split lines and collapse horizontal spaces within each line
    normalized_lines: list[str] = []
    for line in text.split("\n"):
        cleaned_line = re.sub(r"[^\S\n]+", " ", line).strip()
        normalized_lines.append(cleaned_line)

    # Join and collapse 3 or more consecutive newlines into 2 (paragraph boundary)
    result = "\n".join(normalized_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def extract_metadata_field(soup: BeautifulSoup, names: list[str], properties: list[str]) -> str | None:
    """Helper to extract content from meta tags by name or property."""
    for prop in properties:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            content = str(tag.get("content")).strip()
            if content:
                return content

    for name in names:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        if tag and tag.get("content"):
            content = str(tag.get("content")).strip()
            if content:
                return content

    return None


def extract_canonical_url(soup: BeautifulSoup, base_url: str) -> str | None:
    """Find and screen canonical URL from <link rel="canonical"> tag."""
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in (r if isinstance(r, list) else [r]))
    if not canonical_tag or not canonical_tag.get("href"):
        return None

    raw_href = str(canonical_tag.get("href")).strip()
    if not raw_href:
        return None

    # Resolve relative URL against base_url
    resolved_url = urljoin(base_url, raw_href)

    # Validate and screen against SSRF / private IP ranges
    screen_result = validate_and_screen_url(resolved_url)
    if screen_result.is_valid:
        return screen_result.normalized_url

    return None


def extract_language(soup: BeautifulSoup) -> str | None:
    """Extract language from <html lang="..."> or content-language meta."""
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        lang = str(html_tag.get("lang")).strip()
        if lang:
            # Normalize e.g. "en-US" -> "en-US" (or short code "en")
            return lang[:16]

    meta_lang = extract_metadata_field(
        soup,
        names=["language", "content-language"],
        properties=["og:locale"],
    )
    if meta_lang:
        return meta_lang[:16]

    return None


def extract_headings(soup: BeautifulSoup) -> list[dict[str, str | int]]:
    """Extract headings h1-h6 in document order."""
    headings: list[dict[str, str | int]] = []
    heading_tags = soup.find_all(re.compile(r"^h[1-6]$"))
    for h in heading_tags:
        text = h.get_text(separator=" ", strip=True)
        if text:
            headings.append({
                "tag": h.name.lower(),
                "level": int(h.name[1]),
                "text": text,
            })
    return headings


def extract_main_content(soup: BeautifulSoup) -> str:
    """Extract main text content, preferring <article>, <main>, or role=main."""
    # Look for primary content containers
    candidate = soup.find("article")
    if not candidate:
        candidate = soup.find("main")
    if not candidate:
        candidate = soup.find(attrs={"role": "main"})

    # If container is found and has substantial text, extract from candidate
    if candidate and isinstance(candidate, Tag):
        candidate_text = candidate.get_text(separator="\n", strip=True)
        if len(candidate_text) >= 50:
            return normalize_text(candidate_text)

    # Fallback to body or whole document
    body = soup.find("body") or soup
    return normalize_text(body.get_text(separator="\n", strip=True))


def extract_document_data(html: str, url: str) -> ExtractedDocumentData:
    """Extract cleaned, normalized structured data from an HTML page string.

    Args:
        html: Raw HTML string.
        url: URL of the webpage (used for base URL resolution).

    Returns:
        ExtractedDocumentData containing all structured metadata and content.
    """
    if not html or not html.strip():
        return ExtractedDocumentData(
            url=url,
            canonical_url=None,
            title=None,
            description=None,
            main_content="",
            content_hash=hashlib.sha256(b"").hexdigest(),
            word_count=0,
            extraction_status="completed",
        )

    try:
        raw_soup = BeautifulSoup(html, "html.parser")

        # 1. Extract metadata before destructive cleaning
        canonical_url = extract_canonical_url(raw_soup, url)
        language = extract_language(raw_soup)

        # Title: check <title>, og:title, twitter:title, h1
        title = None
        title_tag = raw_soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.get_text(strip=True)
        if not title:
            title = extract_metadata_field(
                raw_soup,
                names=["twitter:title"],
                properties=["og:title"],
            )
        if not title:
            h1 = raw_soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        # Description
        description = extract_metadata_field(
            raw_soup,
            names=["description", "twitter:description"],
            properties=["og:description"],
        )

        # Author
        author = extract_metadata_field(
            raw_soup,
            names=["author", "twitter:creator"],
            properties=["article:author"],
        )

        # Published and modified dates
        published_date = extract_metadata_field(
            raw_soup,
            names=["date", "pubdate", "dc.date"],
            properties=["article:published_time"],
        )
        if not published_date:
            time_tag = raw_soup.find("time", attrs={"datetime": True})
            if time_tag:
                published_date = str(time_tag.get("datetime")).strip()

        modified_date = extract_metadata_field(
            raw_soup,
            names=["last-modified"],
            properties=["article:modified_time", "og:updated_time"],
        )

        # 2. Make a copy for cleaning and extracting main content & headings
        clean_tree = clean_html_soup(copy.copy(raw_soup), remove_boilerplate=True)
        headings = extract_headings(clean_tree)
        main_content = extract_main_content(clean_tree)

        # 3. Calculate content hash & word count
        content_hash = hashlib.sha256(main_content.encode("utf-8")).hexdigest()
        word_count = len(main_content.split()) if main_content else 0

        return ExtractedDocumentData(
            url=url,
            canonical_url=canonical_url,
            title=title,
            description=description,
            main_content=main_content,
            headings=headings,
            language=language,
            author=author,
            published_date=published_date,
            modified_date=modified_date,
            content_hash=content_hash,
            word_count=word_count,
            extraction_status="completed",
        )

    except Exception as exc:
        return ExtractedDocumentData(
            url=url,
            canonical_url=None,
            title=None,
            description=None,
            main_content="",
            content_hash=hashlib.sha256(b"").hexdigest(),
            word_count=0,
            extraction_status="failed",
            error_message=str(exc),
        )
