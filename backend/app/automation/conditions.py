"""Safe declarative workflow condition evaluator (no arbitrary code execution)."""

from __future__ import annotations

from typing import Any


def evaluate_condition(config: dict[str, Any], ctx: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate a validated workflow condition against current execution context.

    Supported condition_type values:
      - results_exist: True if len(sources) > 0
      - min_count: True if len(sources) >= int(threshold)
      - keyword_present: True if keyword (case-insensitive) appears in summary/sources
      - new_info_detected: True if new_sources_count > 0
      - topic_relevant: True if topic appears in retrieved text
    """
    ctype = str(config.get("condition_type", "results_exist")).strip().lower()
    sources: list[dict[str, Any]] = ctx.get("sources", [])

    if ctype == "results_exist":
        passed = len(sources) > 0
        return passed, f"results_exist -> {len(sources)} source(s) found"

    if ctype == "min_count":
        threshold = max(1, int(config.get("threshold", 1)))
        passed = len(sources) >= threshold
        return passed, f"min_count ({len(sources)} >= {threshold}) -> {passed}"

    if ctype == "keyword_present":
        kw = str(config.get("keyword", "")).strip().lower()
        if not kw:
            return False, "keyword_present -> no keyword configured"
        haystack = (
            str(ctx.get("summary_text", ""))
            + " "
            + " ".join(f"{s.get('title', '')} {s.get('snippet', '')}" for s in sources)
        ).lower()
        passed = kw in haystack
        return passed, f"keyword_present ('{kw}') -> {passed}"

    if ctype == "new_info_detected":
        new_cnt = int(ctx.get("new_sources_count", len(sources)))
        passed = new_cnt > 0
        return passed, f"new_info_detected -> {new_cnt} new source(s)"

    if ctype == "topic_relevant":
        topic = str(config.get("topic", ctx.get("topic", ""))).strip().lower()
        if not topic:
            return len(sources) > 0, "topic_relevant (default results check)"
        haystack = " ".join(f"{s.get('title', '')} {s.get('snippet', '')}" for s in sources).lower()
        passed = topic in haystack
        return passed, f"topic_relevant ('{topic}') -> {passed}"

    raise ValueError(f"Unsupported condition_type: '{ctype}'")
