"""Deterministic and optional AI-assisted content classification for Universal Data Intelligence."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.context import ContextBuilder
from app.ai.router import AIProviderRouter
from app.core.logging import get_logger

logger = get_logger("intelligence.classifier")

VALID_CATEGORIES = {
    "research_paper",
    "technical_documentation",
    "report",
    "invoice",
    "resume",
    "book",
    "tutorial",
    "dataset",
    "spreadsheet",
    "article",
    "notes",
    "legal_document",
    "image",
    "general_document",
}

_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("invoice", ("invoice", "bill to", "subtotal", "amount due", "tax id", "payment terms", "invoice #")),
    ("resume", ("curriculum vitae", "work experience", "education", "skills", "references available")),
    ("legal_document", ("whereas", "hereinafter", "jurisdiction", "indemnify", "governing law", "terms of service", "agreement")),
    ("research_paper", ("abstract", "methodology", "references", "et al.", "conclusion", "literature review", "arxiv")),
    ("technical_documentation", ("api reference", "endpoint", "parameters", "configuration", "installation", "sdk", "schema")),
    ("tutorial", ("step 1", "step 2", "how to", "walkthrough", "getting started", "prerequisites")),
    ("report", ("executive summary", "quarterly", "findings", "recommendations", "annual report", "kpi")),
    ("book", ("chapter 1", "table of contents", "isbn", "foreword", "preface")),
    ("notes", ("todo", "meeting notes", "action items", "agenda", "quick notes")),
    ("article", ("published on", "byline", "editorial", "opinion", "read time")),
]


def classify_content_deterministic(
    title: str,
    text: str,
    file_type: str,
    format_kind: str = "document",
) -> tuple[str, float, str]:
    """Classify content deterministically using format + weighted keyword signals."""
    ft = (file_type or "").lower()
    if ft in ("csv", "xlsx"):
        return "spreadsheet", 0.98, "file_format"
    if ft in ("json", "jsonl") or format_kind == "dataset":
        return "dataset", 0.95, "file_format"
    if ft in ("png", "jpg", "jpeg", "webp"):
        return "image", 0.98, "file_format"

    hay = f"{title or ''}\n{(text or '')[:5000]}".lower()
    best_cat = "general_document"
    best_hits = 0

    for category, keywords in _CATEGORY_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in hay)
        if hits > best_hits:
            best_hits = hits
            best_cat = category

    if best_hits >= 2:
        confidence = min(0.92, 0.55 + 0.1 * best_hits)
        return best_cat, confidence, "deterministic_keywords"
    if best_hits == 1:
        return best_cat, 0.52, "deterministic_weak"
    return "general_document", 0.4, "default"


def classify_content(
    title: str,
    text: str,
    file_type: str,
    format_kind: str = "document",
    use_ai: bool = False,
    provider: str = "auto",
    ai_router: AIProviderRouter | None = None,
) -> dict[str, Any]:
    """Classify content deterministically, optionally refining via AIProviderRouter."""
    category, confidence, method = classify_content_deterministic(title, text, file_type, format_kind)

    if use_ai and category in ("general_document", "article") and text.strip():
        router = ai_router or AIProviderRouter()
        sanitizer = ContextBuilder()
        safe_title = sanitizer._sanitize_for_prompt(title or "")
        safe_snippet = sanitizer._sanitize_for_prompt(text[:2500])
        system_prompt = (
            "Classify the document into EXACTLY ONE category from this list: "
            + ", ".join(sorted(VALID_CATEGORIES - {"spreadsheet", "dataset", "image"}))
            + '. Respond strictly with JSON: {"category": "<name>", "confidence": 0.0-1.0}.'
        )
        user_prompt = f"Title: {safe_title}\nContent excerpt:\n{safe_snippet}"
        try:
            resp, _, active = router.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                requested_provider=provider,
                timeout=15.0,
            )
            match = re.search(r"\{.*?\}", resp.content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                ai_cat = str(parsed.get("category", "")).strip().lower()
                if ai_cat in VALID_CATEGORIES:
                    ai_conf = float(parsed.get("confidence", 0.75))
                    return {
                        "category": ai_cat,
                        "confidence": max(0.0, min(1.0, ai_conf)),
                        "method": f"ai:{active}",
                    }
        except Exception as exc:
            logger.debug("AI classification skipped/failed (%s); keeping deterministic result.", type(exc).__name__)

    return {"category": category, "confidence": confidence, "method": method}
