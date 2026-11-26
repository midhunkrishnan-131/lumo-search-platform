"""Shared Source & Evidence Management and Cross-Module Context Isolation for LUMO Phase 27."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any
from urllib.parse import urlparse

from app.ai.context import ContextBuilder

MAX_CONTEXT_CHARS = 8000
_sanitizer = ContextBuilder()


def make_source_record(
    url: str = "",
    title: str = "",
    module: str = "search",
    source_type: str = "document",
    relevance: float | None = None,
    citation_id: str | None = None,
    excerpt: str = "",
    verification_status: str = "unverified",
) -> dict[str, Any]:
    """Create a normalized source & evidence record."""
    clean_url = (url or "").strip()
    domain = urlparse(clean_url).hostname or "" if clean_url else ""
    sid_seed = clean_url or f"{module}:{title}:{excerpt[:64]}"
    source_id = hashlib.sha1(sid_seed.encode("utf-8", errors="replace")).hexdigest()[:12]
    return {
        "source_id": source_id,
        "url": clean_url,
        "title": (title or clean_url or "Untitled Source")[:240],
        "domain": domain,
        "source_type": source_type,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "relevance": round(float(relevance), 4) if relevance is not None else None,
        "citation_id": citation_id,
        "excerpt": _sanitizer._sanitize_for_prompt((excerpt or "")[:500]),
        "verification_status": verification_status,
    }


def deduplicate_sources(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate sources by normalized URL or source_id; return (deduped_list, duplicate_count)."""
    seen: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for src in sources:
        key = (src.get("url") or "").strip().lower() or str(src.get("source_id") or "")
        if not key:
            continue
        if key in seen:
            duplicates += 1
            # Prefer verified status or higher relevance if duplicate
            existing = seen[key]
            if src.get("verification_status") == "verified" and existing.get("verification_status") != "verified":
                existing["verification_status"] = "verified"
            if (src.get("relevance") or 0.0) > (existing.get("relevance") or 0.0):
                existing["relevance"] = src.get("relevance")
        else:
            seen[key] = dict(src)
    return list(seen.values()), duplicates


def detect_disagreements_and_gaps(
    sources: list[dict[str, Any]],
    guardian_urls: list[dict[str, Any]] | None = None,
    citations: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Identify blocked/unverified sources, missing citations, or conflicting evidence signals."""
    findings: list[dict[str, Any]] = []
    for g in (guardian_urls or []):
        if g.get("is_blocked"):
            findings.append({
                "type": "blocked_source",
                "detail": f"URL '{g.get('url', '')}' was blocked by Guardian ({g.get('error', 'security policy')}).",
            })

    if citations:
        known_cids = {str(s.get("citation_id")) for s in sources if s.get("citation_id")}
        for cid in citations:
            if cid not in known_cids:
                findings.append({
                    "type": "unsupported_citation",
                    "detail": f"Citation [{cid}] has no matching retrieved source record.",
                })

    if not sources and citations:
        findings.append({
            "type": "missing_sources",
            "detail": "Citations were referenced without retrieved source records.",
        })
    return findings


class CrossModuleContext:
    """Controlled, size-bounded context passed between workflow steps with prompt-injection isolation."""

    def __init__(self, max_chars: int = MAX_CONTEXT_CHARS) -> None:
        self.max_chars = max_chars
        self._sections: dict[str, str] = {}
        self.sources: list[dict[str, Any]] = []

    def add_text(self, module_name: str, text: str) -> None:
        if not text:
            return
        safe = _sanitizer._sanitize_for_prompt(text[: self.max_chars])
        self._sections[module_name] = safe[: self.max_chars]

    def add_source(self, source: dict[str, Any]) -> None:
        self.sources.append(source)

    def get_combined_text(self, modules: list[str] | None = None) -> str:
        parts: list[str] = []
        total = 0
        for mod, txt in self._sections.items():
            if modules and mod not in modules:
                continue
            remaining = self.max_chars - total
            if remaining <= 0:
                break
            chunk = txt[:remaining]
            parts.append(f"[{mod}]\n{chunk}")
            total += len(chunk)
        return "\n\n".join(parts)
