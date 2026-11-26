"""Live Public Internet Search Provider Abstraction & SSRF-Safe Webpage Extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from typing import Any, Protocol
from urllib.parse import quote, urljoin, urlparse

import httpx

from app.core.logging import get_logger
from app.guardian.validator import validate_guardian_url
from app.processor.extractor import extract_document_data

logger = get_logger("search.web_provider")


@dataclass
class WebSearchResult:
    id: str
    title: str
    url: str
    domain: str
    snippet: str
    source_provider: str
    published_at: str | None = None
    score: float = 0.0


class BaseWebSearchProvider(Protocol):
    name: str

    def search(self, query: str, page: int = 1, per_page: int = 8) -> list[WebSearchResult]: ...


def _strip_html_tags(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw or "")).strip()


class PublicMultiWebSearchProvider:
    """Zero-cost live internet search combining Wikipedia Search API, HN Algolia API, and DDG IA."""

    name = "public_multi_web"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def search(self, query: str, page: int = 1, per_page: int = 8) -> list[WebSearchResult]:
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        # Extract optional site:domain filter
        site_filter: str | None = None
        m_site = re.search(r"\bsite:([A-Za-z0-9.-]+)", clean_q, re.IGNORECASE)
        if m_site:
            site_filter = m_site.group(1).lower()
            clean_q_no_site = re.sub(r"\bsite:[A-Za-z0-9.-]+", "", clean_q, flags=re.IGNORECASE).strip() or site_filter
        else:
            clean_q_no_site = clean_q

        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        offset = max(0, (page - 1) * per_page)
        provider_errors: list[str] = []
        attempted = 0

        with httpx.Client(timeout=self.timeout, headers={"User-Agent": "LUMO-Search/1.0"}) as client:
            # 1. Hacker News Algolia API (real-time tech/news/programming & general web links)
            attempted += 1
            try:
                hn_resp = client.get(
                    "https://hn.algolia.com/api/v1/search",
                    params={"query": clean_q_no_site, "page": max(0, page - 1), "hitsPerPage": per_page},
                )
                if hn_resp.status_code == 200:
                    for idx, hit in enumerate(hn_resp.json().get("hits") or []):
                        url = (hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}").strip()
                        title = (hit.get("title") or hit.get("story_title") or "").strip()
                        if not title or not url:
                            continue
                        dom = (urlparse(url).hostname or "").lower()
                        if site_filter and site_filter not in dom:
                            continue
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        snippet = _strip_html_tags(hit.get("story_text") or hit.get("comment_text") or f"Source: {dom} · Author: {hit.get('author', 'community')}")
                        results.append(WebSearchResult(
                            id=f"web_hn_{hit.get('objectID', idx)}",
                            title=title[:240],
                            url=url,
                            domain=dom,
                            snippet=snippet[:320],
                            source_provider="hn_algolia",
                            published_at=hit.get("created_at"),
                            score=round(max(0.1, 1.0 - idx * 0.05), 3),
                        ))
                else:
                    provider_errors.append(f"hn_algolia HTTP {hn_resp.status_code}")
            except Exception as exc:
                logger.warning("HN Algolia search failed (%s)", type(exc).__name__)
                provider_errors.append(f"hn_algolia {type(exc).__name__}")

            # 2. Wikipedia OpenSearch / Query API (real encyclopedic/reference web results)
            if not site_filter or "wikipedia.org" in site_filter:
                attempted += 1
                try:
                    wiki_resp = client.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "list": "search",
                            "srsearch": clean_q_no_site,
                            "sroffset": offset,
                            "srlimit": per_page,
                            "format": "json",
                        },
                    )
                    if wiki_resp.status_code == 200:
                        for idx, item in enumerate(wiki_resp.json().get("query", {}).get("search", [])):
                            title = (item.get("title") or "").strip()
                            if not title:
                                continue
                            url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                            if url in seen_urls:
                                continue
                            seen_urls.add(url)
                            snippet = _strip_html_tags(item.get("snippet") or "")
                            results.append(WebSearchResult(
                                id=f"web_wiki_{item.get('pageid', idx)}",
                                title=f"{title} — Wikipedia",
                                url=url,
                                domain="en.wikipedia.org",
                                snippet=snippet[:320],
                                source_provider="wikipedia",
                                published_at=item.get("timestamp"),
                                score=round(max(0.1, 0.95 - idx * 0.04), 3),
                            ))
                    else:
                        provider_errors.append(f"wikipedia HTTP {wiki_resp.status_code}")
                except Exception as exc:
                    logger.warning("Wikipedia search failed (%s)", type(exc).__name__)
                    provider_errors.append(f"wikipedia {type(exc).__name__}")

        if not results and len(provider_errors) >= attempted and attempted > 0:
            raise RuntimeError(f"Live web search providers failed: {'; '.join(provider_errors)}")

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:per_page]


def fetch_and_extract_webpage(url: str, timeout: float = 8.0, max_bytes: int = 512 * 1024) -> dict[str, Any]:
    """Safely fetch and extract readable text from a public webpage with redirect-SSRF protection."""
    current_url = (url or "").strip()
    max_hops = 3

    with httpx.Client(timeout=timeout, headers={"User-Agent": "LUMO-Extractor/1.0"}) as client:
        for _ in range(max_hops + 1):
            val = validate_guardian_url(current_url, resolve_dns=True)
            if not val.is_valid or val.is_blocked:
                raise ValueError(val.error or "URL blocked by SSRF security policy.")

            resp = client.get(val.normalized_url, follow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location")
                if not loc:
                    raise ValueError("Redirect missing Location header.")
                current_url = urljoin(val.normalized_url, loc)
                continue

            if resp.status_code >= 400:
                raise ValueError(f"Remote server returned HTTP {resp.status_code}.")

            raw = resp.content[:max_bytes]
            text_html = raw.decode(resp.encoding or "utf-8", errors="replace")
            extracted = extract_document_data(text_html, val.normalized_url)
            return {
                "url": val.normalized_url,
                "domain": val.hostname,
                "title": extracted.title,
                "description": extracted.description,
                "main_content": extracted.main_content[:6000],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

    raise ValueError("Too many redirects.")


live_web_provider = PublicMultiWebSearchProvider()
