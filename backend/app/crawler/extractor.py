"""HTML link extraction and metadata parsing.

Extracts anchor tags, resolves relative links, strips fragment identifiers,
and rejects non-web schemes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from app.crawler.validator import ALLOWED_SCHEMES, normalize_url


@dataclass
class ExtractedPage:
    title: str = ""
    links: list[str] = field(default_factory=list)


class _LinkAndTitleParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.raw_links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = True
        elif tag_lower == "a":
            for attr_name, attr_val in attrs:
                if attr_name.lower() == "href" and attr_val:
                    self.raw_links.append(attr_val.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def extract_links_from_html(html_text: str, base_url: str) -> ExtractedPage:
    """Parse HTML string and return sanitized, unique links and page title."""
    if not html_text:
        return ExtractedPage()

    parser = _LinkAndTitleParser(base_url)
    try:
        parser.feed(html_text)
    except Exception:
        # html.parser is lenient, but guard against malformed data
        pass

    raw_title = " ".join("".join(parser.title_parts).split()).strip()
    seen: set[str] = set()
    valid_links: list[str] = []

    for raw_href in parser.raw_links:
        # Discard obvious non-web schemes
        href_lower = raw_href.lower()
        if (
            href_lower.startswith("javascript:")
            or href_lower.startswith("mailto:")
            or href_lower.startswith("tel:")
            or href_lower.startswith("data:")
            or href_lower.startswith("file:")
            or href_lower.startswith("#")
        ):
            continue

        try:
            absolute = urljoin(base_url, raw_href)
            parsed = urlparse(absolute)
            if parsed.scheme.lower() not in ALLOWED_SCHEMES:
                continue

            normalized = normalize_url(absolute)
            if normalized not in seen:
                seen.add(normalized)
                valid_links.append(normalized)
        except Exception:
            continue

    return ExtractedPage(title=raw_title, links=valid_links)
