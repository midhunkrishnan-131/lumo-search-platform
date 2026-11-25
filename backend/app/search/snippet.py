"""Safe search snippet generation and term highlighting."""

from __future__ import annotations

import html
import re


def generate_snippet(
    text: str,
    query: str,
    max_chars: int = 240,
    highlight_tag: str = "b",
) -> str:
    """Extract a representative text snippet centered on query terms with safe HTML escaping.

    Args:
        text: Raw document content or description.
        query: User search query.
        max_chars: Target maximum character length for snippet.
        highlight_tag: HTML tag to wrap matching terms (e.g. 'b' or 'mark').

    Returns:
        HTML-safe snippet string with highlighted terms.
    """
    if not text:
        return ""

    # Clean whitespace in text
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return ""

    # Extract alphanumeric query terms (ignoring 1-character words)
    terms = [re.escape(t) for t in re.findall(r"\w+", query) if len(t) > 1]
    if not terms:
        # No query terms: return beginning of text safely escaped
        trimmed = clean_text[:max_chars]
        if len(clean_text) > max_chars:
            trimmed = trimmed.rsplit(" ", 1)[0] + "..."
        return html.escape(trimmed)

    pattern = re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)

    # Find the earliest matching query term in the text
    match = pattern.search(clean_text)
    if not match:
        # Fallback to simple beginning of text
        trimmed = clean_text[:max_chars]
        if len(clean_text) > max_chars:
            trimmed = trimmed.rsplit(" ", 1)[0] + "..."
        return html.escape(trimmed)

    # Center window around match
    match_start = match.start()
    half_window = max_chars // 2

    start_idx = max(0, match_start - half_window)
    end_idx = min(len(clean_text), start_idx + max_chars)

    # Adjust window if end reached early
    if end_idx - start_idx < max_chars and start_idx > 0:
        start_idx = max(0, end_idx - max_chars)

    # Word boundary alignment
    prefix = ""
    suffix = ""

    if start_idx > 0:
        prefix = "..."
        # Advance to first complete word
        space_idx = clean_text.find(" ", start_idx)
        if 0 < space_idx < match_start:
            start_idx = space_idx + 1

    if end_idx < len(clean_text):
        suffix = "..."
        # Cut back to last complete word
        space_idx = clean_text.rfind(" ", start_idx, end_idx)
        if space_idx > match_start:
            end_idx = space_idx

    snippet_raw = clean_text[start_idx:end_idx].strip()

    # HTML escape the snippet first
    escaped_snippet = html.escape(snippet_raw)

    # Safely apply highlight tags around matching terms
    escaped_terms = [re.escape(html.escape(t)) for t in re.findall(r"\w+", query) if len(t) > 1]
    if escaped_terms:
        highlight_pattern = re.compile(r"\b(" + "|".join(escaped_terms) + r")\b", re.IGNORECASE)
        highlighted = highlight_pattern.sub(f"<{highlight_tag}>\\1</{highlight_tag}>", escaped_snippet)
    else:
        highlighted = escaped_snippet

    return f"{prefix}{highlighted}{suffix}"
