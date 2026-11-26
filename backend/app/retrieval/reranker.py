"""Modular Reranking Engine with Bounded Candidates, Timeout, Cancellation & Explanations (Phase 29)."""

from __future__ import annotations

import re
import time
from typing import Any, Callable


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 10,
    max_candidates: int = 50,
    timeout_seconds: float = 5.0,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """Reorder bounded candidates using deterministic lexical, phrase, and metadata signals."""
    if not candidates:
        return []
    started = time.monotonic()
    q_low = (query or "").strip().lower()
    q_terms = {t for t in re.findall(r"[a-z0-9]+", q_low) if len(t) > 1}
    bounded = candidates[:max_candidates]
    reranked: list[dict[str, Any]] = []

    for item in bounded:
        if cancel_check and cancel_check():
            break
        if (time.monotonic() - started) > timeout_seconds:
            break

        title = str(item.get("title") or "").lower()
        snippet = str(item.get("snippet") or "").lower()
        combined = f"{title} {snippet}"

        base_score = float(item.get("score") or 0.0)
        # Normalize base score gently to [0, 1] range contribution
        norm_base = min(1.0, max(0.0, base_score * 10.0)) if base_score < 0.2 else min(1.0, base_score)
        term_hits = sum(1 for t in q_terms if t in combined)
        term_cov = (term_hits / len(q_terms)) if q_terms else 0.0
        phrase_boost = 0.25 if (q_low and q_low in combined) else 0.0
        title_boost = 0.15 if any(t in title for t in q_terms) else 0.0

        final_score = round(0.45 * norm_base + 0.35 * term_cov + phrase_boost + title_boost, 4)

        explanations = list(item.get("explanations") or [])
        if term_hits > 0 and "Keyword match" not in explanations:
            explanations.append("Keyword match")
        if "Reranking" not in explanations:
            explanations.append("Reranking")

        copy_item = dict(item)
        copy_item["rerank_score"] = final_score
        copy_item["explanations"] = explanations
        reranked.append(copy_item)

    reranked.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return reranked[:top_k]
