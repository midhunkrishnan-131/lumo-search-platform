"""Deterministic, bounded Adaptive Search Ranking service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.personalization.topics import normalize_topic


@dataclass
class RankedResultAdjustment:
    item_id: str
    original_score: float
    adjusted_score: float
    explanation: str | None = None
    applied_signals: list[str] = field(default_factory=list)


class AdaptiveRanker:
    """Applies bounded, explainable ranking adjustments without overriding core query relevance."""

    MAX_DELTA = 0.35  # Hard bound: personalization cannot swing score beyond +/- 35% * weight

    def rerank(
        self,
        results: list[Any],
        enabled: bool,
        personalization_weight: float,
        interests: list[dict[str, Any]],
        topics: list[dict[str, Any]],
        source_prefs: list[dict[str, Any]],
        feedback_items: list[dict[str, Any]],
    ) -> tuple[list[Any], list[RankedResultAdjustment]]:
        """Rerank search results deterministically when enabled; return untouched baseline when disabled."""
        if not enabled or not results or personalization_weight <= 0:
            return results, []

        weight = max(0.0, min(0.5, float(personalization_weight)))

        followed_topics = {
            normalize_topic(i["topic"]): float(i.get("weight", 1.0))
            for i in interests
            if i.get("source") in ("explicit", "followed")
        }
        excluded_topics = {
            normalize_topic(i["topic"])
            for i in interests
            if i.get("source") == "excluded"
        }
        repeated_topics = {
            normalize_topic(t["topic"]): float(t.get("confidence", 0.5))
            for t in topics
            if t.get("signal_kind") == "repeated"
        }

        preferred_domains = {
            s["domain"].lower(): float(s.get("weight", 1.0))
            for s in source_prefs
            if s.get("preference") == "preferred"
        }
        excluded_domains = {
            s["domain"].lower()
            for s in source_prefs
            if s.get("preference") == "excluded"
        }

        liked_urls = {f["target_url"] for f in feedback_items if f.get("feedback_type") in ("relevant", "helpful") and f.get("target_url")}
        disliked_urls = {f["target_url"] for f in feedback_items if f.get("feedback_type") in ("not_relevant", "not_helpful") and f.get("target_url")}

        scored: list[tuple[int, float, Any, RankedResultAdjustment]] = []
        total_n = len(results)

        for idx, item in enumerate(results):
            # Support both Pydantic/ORM objects and dicts
            raw_score = getattr(item, "score", None)
            if raw_score is None:
                # Derive deterministic baseline score from original rank position
                raw_score = float(total_n - idx) / max(1, total_n)

            url = getattr(item, "url", "") or ""
            domain = (getattr(item, "domain", None) or urlparse(url).netloc).lower()
            title = getattr(item, "title", "") or ""
            snippet = getattr(item, "snippet", "") or getattr(item, "description", "") or ""
            haystack = f"{title} {snippet}".lower()
            item_id = str(getattr(item, "id", idx))

            delta = 0.0
            signals: list[str] = []
            reasons: list[str] = []

            # 1. Domain preferences (separate from trustworthiness)
            if domain in excluded_domains:
                delta -= 0.35
                signals.append("excluded_source")
                reasons.append(f"Demoted: excluded domain ({domain})")
            elif domain in preferred_domains:
                delta += 0.18 * preferred_domains[domain]
                signals.append("preferred_source")
                reasons.append(f"Matches preferred source ({domain})")

            # 2. Explicit & followed topics vs excluded topics
            for exc_t in excluded_topics:
                if exc_t and exc_t in haystack:
                    delta -= 0.30
                    signals.append("excluded_topic")
                    reasons.append(f"Demoted: hidden topic ({exc_t})")
                    break

            for fol_t, w in followed_topics.items():
                if fol_t and fol_t in haystack:
                    delta += 0.20 * min(1.5, w)
                    signals.append(f"followed_topic:{fol_t}")
                    reasons.append(f"Connected to a topic you follow ({fol_t})")
                    break

            # 3. Repeated topic exploration (bounded smaller boost than explicit)
            if not any(s.startswith("followed_topic:") for s in signals):
                for rep_t, conf in repeated_topics.items():
                    if rep_t and rep_t in haystack:
                        delta += 0.10 * conf
                        signals.append(f"repeated_topic:{rep_t}")
                        reasons.append("Connected to a topic you frequently explore")
                        break

            # 4. Explicit feedback on URL
            if url in liked_urls:
                delta += 0.15
                signals.append("positive_feedback")
                reasons.append("Recommended based on explicit feedback")
            elif url in disliked_urls:
                delta -= 0.25
                signals.append("negative_feedback")
                reasons.append("Demoted based on explicit feedback")

            # Clamp delta strictly to [-MAX_DELTA, +MAX_DELTA]
            clamped_delta = max(-self.MAX_DELTA, min(self.MAX_DELTA, delta))
            adjusted = round(float(raw_score) * (1.0 + clamped_delta * weight), 6)

            adj = RankedResultAdjustment(
                item_id=item_id,
                original_score=float(raw_score),
                adjusted_score=adjusted,
                explanation="; ".join(reasons) if reasons else "Matches your current search",
                applied_signals=signals,
            )
            scored.append((idx, adjusted, item, adj))

        scored.sort(key=lambda row: (-row[1], row[0]))
        return [row[2] for row in scored], [row[3] for row in scored]
