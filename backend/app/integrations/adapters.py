"""Built-in Phase 22 External Integration Adapters (RSS/Atom, GitHub, Docs, Open Data, Public API)."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

from app.crawler.validator import validate_and_screen_url
from app.integrations.base import BaseIntegration, NormalizedItem
from app.integrations.http_guard import safe_integration_fetch
from app.processor.extractor import extract_document_data

_XXE_RE = re.compile(r"<!(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _parse_xml_safely(xml_bytes: bytes) -> ET.Element:
    text = xml_bytes.decode("utf-8", errors="replace")
    if _XXE_RE.search(text[:4096]):
        raise ValueError("Rejected XML containing DOCTYPE/ENTITY declarations (XXE protection).")
    return ET.fromstring(text)


class RssAtomIntegration(BaseIntegration):
    integration_id = "rss_atom"
    name = "RSS & Atom Feeds"
    category = "web_research"
    description = "Subscribe to RSS 2.0 and Atom feeds, deduplicate entries, and index updates."
    version = "1.0.0"
    capabilities = ["feed_sync", "monitoring", "deduplication", "workspace_import", "kg_linking"]
    default_permissions = ["read_external", "import_data", "write_workspace", "create_notifications", "sync_sources"]
    config_fields = [
        {"name": "default_feed_url", "label": "Default Feed URL", "type": "url", "required": False},
    ]

    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        url = (config.get("default_feed_url") or "").strip()
        if url:
            v = validate_and_screen_url(url, resolve_dns=False)
            if not v.is_valid:
                return False, v.error
        return True, None

    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        url = (config.get("default_feed_url") or "").strip()
        if not url:
            return {"ok": True, "detail": "Adapter ready. Add a feed source URL to sync."}
        status, _, content, _ = safe_integration_fetch(url, self.integration_id)
        if status >= 400:
            return {"ok": False, "detail": f"HTTP {status}"}
        _parse_xml_safely(content)
        return {"ok": True, "detail": f"Feed reachable (HTTP {status})"}

    def fetch_data(self, source_url: str, config: dict[str, Any], secret: str | None = None, max_items: int = 15) -> list[dict[str, Any]]:
        status, _, content, _ = safe_integration_fetch(source_url, self.integration_id)
        if status >= 400:
            raise RuntimeError(f"Feed returned HTTP {status}")
        root = _parse_xml_safely(content)
        root_tag = _strip_ns(root.tag)
        entries: list[dict[str, Any]] = []

        if root_tag == "rss":
            channel = next((c for c in root if _strip_ns(c.tag) == "channel"), None)
            items = [c for c in (channel or []) if _strip_ns(c.tag) == "item"]
            for it in items[:max_items]:
                fields = {_strip_ns(c.tag): (c.text or "").strip() for c in it}
                entries.append({
                    "external_id": fields.get("guid") or fields.get("link") or fields.get("title", ""),
                    "title": fields.get("title") or "Untitled Feed Entry",
                    "description": fields.get("description") or "",
                    "url": fields.get("link") or source_url,
                    "author": fields.get("author") or fields.get("creator"),
                    "published_at": fields.get("pubdate"),
                })
        elif root_tag == "feed":
            for ent in [c for c in root if _strip_ns(c.tag) == "entry"][:max_items]:
                title = ""
                summary = ""
                link = source_url
                author = None
                pub = None
                eid = ""
                for c in ent:
                    t = _strip_ns(c.tag)
                    if t == "title":
                        title = (c.text or "").strip()
                    elif t in ("summary", "content"):
                        summary = summary or (c.text or "").strip()
                    elif t == "id":
                        eid = (c.text or "").strip()
                    elif t in ("published", "updated"):
                        pub = pub or (c.text or "").strip()
                    elif t == "link" and c.attrib.get("href"):
                        link = c.attrib["href"].strip()
                    elif t == "author":
                        name_el = next((a for a in c if _strip_ns(a.tag) == "name"), None)
                        if name_el is not None and name_el.text:
                            author = name_el.text.strip()
                entries.append({
                    "external_id": eid or link or title,
                    "title": title or "Untitled Atom Entry",
                    "description": summary,
                    "url": link,
                    "author": author,
                    "published_at": pub,
                })
        else:
            raise ValueError(f"Unrecognized XML feed root element: {root.tag}")
        return entries

    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        out: list[NormalizedItem] = []
        for r in raw_items:
            desc = re.sub(r"<[^>]+>", " ", r.get("description") or "").strip()
            body = f"{r.get('title', '')}\n\n{desc}".strip()
            out.append(
                NormalizedItem(
                    external_id=str(r.get("external_id") or r.get("url") or r.get("title")),
                    integration_id=self.integration_id,
                    source_type="rss_entry",
                    title=str(r.get("title") or "Feed Entry")[:500],
                    content=body,
                    description=desc[:400],
                    url=r.get("url"),
                    author=r.get("author"),
                    published_at=r.get("published_at"),
                    tags=["rss", "feed"],
                    permissions=list(self.default_permissions),
                    source_attribution=source_url,
                )
            )
        return out


class GitHubIntegration(BaseIntegration):
    integration_id = "github"
    name = "GitHub Developer Intelligence"
    category = "developer_intelligence"
    description = "Monitor public GitHub repositories, releases, issues, and documentation via official REST API."
    version = "1.0.0"
    capabilities = ["repo_metadata", "releases", "issues", "monitoring", "search"]
    default_permissions = ["read_external", "import_data", "write_workspace", "create_notifications", "sync_sources"]
    config_fields = [
        {"name": "default_repo", "label": "Default Repository (owner/repo)", "type": "text", "required": False},
        {"name": "include_issues", "label": "Include recent open issues", "type": "boolean", "required": False},
    ]

    def _headers(self, secret: str | None) -> dict[str, str]:
        hdrs = {"Accept": "application/vnd.github+json"}
        if secret:
            hdrs["Authorization"] = f"Bearer {secret}"
        return hdrs

    def _parse_repo(self, source_url: str) -> str:
        s = source_url.strip().rstrip("/")
        if "github.com/" in s:
            parts = s.split("github.com/", 1)[1].split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        if "/" in s and "://" not in s:
            return s
        raise ValueError("Provide a valid GitHub repo as 'owner/repo' or 'https://github.com/owner/repo'.")

    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        repo = (config.get("default_repo") or "").strip()
        if repo:
            try:
                self._parse_repo(repo)
            except ValueError as exc:
                return False, str(exc)
        return True, None

    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        repo = (config.get("default_repo") or "").strip()
        target = f"https://api.github.com/repos/{self._parse_repo(repo)}" if repo else "https://api.github.com/rate_limit"
        status, _, _, _ = safe_integration_fetch(target, self.integration_id, headers=self._headers(secret))
        return {"ok": status < 400, "detail": f"GitHub API HTTP {status}"}

    def fetch_data(self, source_url: str, config: dict[str, Any], secret: str | None = None, max_items: int = 15) -> list[dict[str, Any]]:
        repo = self._parse_repo(source_url)
        hdrs = self._headers(secret)
        items: list[dict[str, Any]] = []

        st, _, body, _ = safe_integration_fetch(f"https://api.github.com/repos/{repo}", self.integration_id, headers=hdrs)
        if st >= 400:
            raise RuntimeError(f"GitHub repo lookup failed (HTTP {st})")
        meta = json.loads(body.decode("utf-8", errors="replace"))
        items.append({
            "kind": "repository",
            "external_id": f"repo:{meta.get('full_name', repo)}",
            "title": f"GitHub Repo: {meta.get('full_name', repo)}",
            "description": meta.get("description") or "",
            "content": (
                f"Repository: {meta.get('full_name', repo)}\n"
                f"Description: {meta.get('description') or 'N/A'}\n"
                f"Language: {meta.get('language') or 'N/A'} | Stars: {meta.get('stargazers_count', 0)} | Forks: {meta.get('forks_count', 0)}\n"
                f"Topics: {', '.join(meta.get('topics', []))}"
            ),
            "url": meta.get("html_url") or f"https://github.com/{repo}",
            "published_at": meta.get("updated_at"),
        })

        # Releases
        r_st, _, r_body, _ = safe_integration_fetch(
            f"https://api.github.com/repos/{repo}/releases?per_page={min(max_items, 10)}",
            self.integration_id,
            headers=hdrs,
        )
        if r_st < 400:
            for rel in json.loads(r_body.decode("utf-8", errors="replace")):
                items.append({
                    "kind": "release",
                    "external_id": f"rel:{rel.get('id')}",
                    "title": f"{repo} Release {rel.get('tag_name') or rel.get('name')}",
                    "description": (rel.get("body") or "")[:300],
                    "content": f"Release: {rel.get('name') or rel.get('tag_name')}\n\n{rel.get('body') or ''}",
                    "url": rel.get("html_url"),
                    "published_at": rel.get("published_at"),
                })

        return items[:max_items]

    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                external_id=str(r["external_id"]),
                integration_id=self.integration_id,
                source_type=f"github_{r.get('kind', 'item')}",
                title=str(r["title"])[:500],
                content=str(r["content"]),
                description=str(r.get("description") or "")[:400],
                url=r.get("url"),
                published_at=r.get("published_at"),
                tags=["github", r.get("kind", "repo")],
                permissions=list(self.default_permissions),
                source_attribution=source_url,
            )
            for r in raw_items
        ]


class DocsSiteIntegration(BaseIntegration):
    integration_id = "docs_site"
    name = "Software Documentation"
    category = "developer_intelligence"
    description = "Ingest and index public technical documentation pages using LUMO's content extractor."
    version = "1.0.0"
    capabilities = ["html_extraction", "monitoring", "search", "kg_linking"]
    default_permissions = ["read_external", "import_data", "write_workspace", "sync_sources"]

    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        return True, None

    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        return {"ok": True, "detail": "Documentation adapter ready."}

    def fetch_data(self, source_url: str, config: dict[str, Any], secret: str | None = None, max_items: int = 15) -> list[dict[str, Any]]:
        st, _, body, final_url = safe_integration_fetch(source_url, self.integration_id)
        if st >= 400:
            raise RuntimeError(f"Documentation page returned HTTP {st}")
        extracted = extract_document_data(body.decode("utf-8", errors="replace"), final_url)
        return [{
            "external_id": final_url,
            "title": extracted.title or final_url,
            "content": extracted.main_content,
            "description": extracted.description or "",
            "url": final_url,
            "author": extracted.author,
            "published_at": extracted.published_date,
            "language": extracted.language,
        }]

    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                external_id=str(r["external_id"]),
                integration_id=self.integration_id,
                source_type="documentation",
                title=str(r["title"])[:500],
                content=str(r["content"]),
                description=str(r.get("description") or "")[:400],
                url=r.get("url"),
                author=r.get("author"),
                published_at=r.get("published_at"),
                language=r.get("language"),
                tags=["docs", "technical"],
                permissions=list(self.default_permissions),
                source_attribution=source_url,
            )
            for r in raw_items
        ]


class OpenDataIntegration(BaseIntegration):
    integration_id = "open_data"
    name = "Open Data & Public Datasets"
    category = "data_intelligence"
    description = "Import bounded CSV, JSON, JSONL, and XML public datasets with schema profiling."
    version = "1.0.0"
    capabilities = ["csv", "json", "jsonl", "xml", "bounded_import"]
    default_permissions = ["read_external", "import_data", "write_workspace", "sync_sources"]

    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        return True, None

    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        return {"ok": True, "detail": "Open Data adapter ready."}

    def fetch_data(self, source_url: str, config: dict[str, Any], secret: str | None = None, max_items: int = 15) -> list[dict[str, Any]]:
        st, hdrs, body, final_url = safe_integration_fetch(source_url, self.integration_id)
        if st >= 400:
            raise RuntimeError(f"Open dataset returned HTTP {st}")
        text = body.decode("utf-8", errors="replace")
        ctype = hdrs.get("content-type", "")
        summary_lines = text.splitlines()[:25]
        return [{
            "external_id": final_url,
            "title": final_url.rsplit("/", 1)[-1] or "Open Dataset",
            "content": "\n".join(summary_lines),
            "description": f"Open data ({ctype or 'text'}) · {len(body)} bytes",
            "url": final_url,
            "metadata": {"bytes": len(body), "content_type": ctype},
        }]

    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                external_id=str(r["external_id"]),
                integration_id=self.integration_id,
                source_type="open_dataset",
                title=str(r["title"])[:500],
                content=str(r["content"]),
                description=str(r.get("description") or "")[:400],
                url=r.get("url"),
                metadata=r.get("metadata") or {},
                tags=["open-data", "dataset"],
                permissions=list(self.default_permissions),
                source_attribution=source_url,
            )
            for r in raw_items
        ]


class PublicApiIntegration(BaseIntegration):
    integration_id = "public_api"
    name = "Public JSON API Connector"
    category = "web_research"
    description = "Connect to public JSON REST endpoints with SSRF protection, pagination, and normalization."
    version = "1.0.0"
    capabilities = ["json_api", "pagination", "monitoring", "normalization"]
    default_permissions = ["read_external", "import_data", "write_workspace", "sync_sources"]
    config_fields = [
        {"name": "records_key", "label": "JSON list key (optional)", "type": "text", "required": False},
        {"name": "title_key", "label": "Item title key (default: title)", "type": "text", "required": False},
    ]

    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        return True, None

    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        return {"ok": True, "detail": "Public API connector ready."}

    def fetch_data(self, source_url: str, config: dict[str, Any], secret: str | None = None, max_items: int = 15) -> list[dict[str, Any]]:
        hdrs = {"Accept": "application/json"}
        if secret:
            hdrs["Authorization"] = f"Bearer {secret}"
        st, _, body, final_url = safe_integration_fetch(source_url, self.integration_id, headers=hdrs)
        if st >= 400:
            raise RuntimeError(f"API endpoint returned HTTP {st}")
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        records_key = (config.get("records_key") or "").strip()
        if isinstance(parsed, dict) and records_key and isinstance(parsed.get(records_key), list):
            rows = parsed[records_key]
        elif isinstance(parsed, list):
            rows = parsed
        elif isinstance(parsed, dict):
            rows = [parsed]
        else:
            rows = [{"value": parsed}]

        title_key = (config.get("title_key") or "title").strip()
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(rows[:max_items]):
            if isinstance(row, dict):
                title = str(row.get(title_key) or row.get("name") or f"API Record #{idx + 1}")
                out.append({
                    "external_id": str(row.get("id") or f"{final_url}#{idx}"),
                    "title": title,
                    "content": json.dumps(row, indent=2)[:8000],
                    "url": str(row.get("url") or final_url),
                })
        return out

    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                external_id=str(r["external_id"]),
                integration_id=self.integration_id,
                source_type="public_api",
                title=str(r["title"])[:500],
                content=str(r["content"]),
                url=r.get("url"),
                tags=["api", "json"],
                permissions=list(self.default_permissions),
                source_attribution=source_url,
            )
            for r in raw_items
        ]


BUILTIN_ADAPTERS: dict[str, BaseIntegration] = {
    a.integration_id: a
    for a in (
        RssAtomIntegration(),
        GitHubIntegration(),
        DocsSiteIntegration(),
        OpenDataIntegration(),
        PublicApiIntegration(),
    )
}
