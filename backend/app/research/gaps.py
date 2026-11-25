"""Gap Detector: Evaluates research gaps and synthesizes follow-up queries."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.router import AIProviderRouter, ai_provider_router
from app.core.logging import get_logger
from app.schemas.research import ResearchFindingItem, ResearchPlan

logger = get_logger("research.gaps")

GAP_SYSTEM_PROMPT = """You are the LUMO Research Gap Detector.
Compare the research objectives, subquestions, and current findings to identify remaining information gaps.
Generate 1 to 3 targeted, specific search queries to address those gaps.

Output STRICT JSON:
{
  "gaps_identified": ["gap 1", "gap 2"],
  "follow_up_queries": ["specific search query 1", "specific search query 2"]
}

Rules:
- Queries must be concise keywords for a search engine.
- Only address gaps directly relevant to the original topic.
- Do not repeat previous queries.
"""


class GapDetector:
    """Identifies remaining gaps and formulates follow-up queries within budget limits."""

    def __init__(self, router: AIProviderRouter | None = None) -> None:
        self.router = router or ai_provider_router

    def detect_gaps_and_queries(
        self,
        plan: ResearchPlan,
        findings: list[ResearchFindingItem],
        executed_queries: set[str],
        max_new_queries: int = 3,
        provider: str = "auto",
    ) -> list[str]:
        """Generate targeted follow-up queries to resolve gaps."""
        if max_new_queries <= 0:
            return []

        gap_findings = [f for f in findings if f.kind == "Information Gap"]
        if not gap_findings:
            # If all subquestions appear answered, no new queries needed
            return []

        prompt_gaps = "\n".join(f"- {g.text}" for g in gap_findings)
        prompt_queries = "\n".join(f"- {q}" for q in executed_queries)
        norm_executed = {q.strip().lower() for q in executed_queries}

        user_prompt = f"""Topic: {plan.topic}

Current Gaps:
{prompt_gaps}

Previously Executed Queries:
{prompt_queries}

Generate follow-up search queries to resolve these gaps:"""

        try:
            resp, _, _ = self.router.execute(
                system_prompt=GAP_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                requested_provider=provider,
            )
            parsed = self._parse_json(resp.content)
            candidates: list[str] = []
            if isinstance(parsed, dict) and "follow_up_queries" in parsed:
                candidates = parsed.get("follow_up_queries", [])
            elif isinstance(parsed, list):
                candidates = [str(x) for x in parsed if isinstance(x, str)]

            if candidates:
                valid_new = []
                for c in candidates:
                    cq = c.strip()
                    if cq and cq.lower() not in norm_executed:
                        valid_new.append(cq)
                        norm_executed.add(cq.lower())
                        if len(valid_new) >= max_new_queries:
                            break
                if valid_new:
                    return valid_new
        except Exception as exc:
            logger.debug("AI gap detection query generation failed (%s), using deterministic fallback", exc)

        return self._fallback_queries(plan, executed_queries, max_new_queries)

    def _fallback_queries(
        self,
        plan: ResearchPlan,
        executed_queries: set[str],
        limit: int,
    ) -> list[str]:
        """Deterministic follow-up queries based on subquestions."""
        candidates = []
        for subq in plan.subquestions:
            # Strip question mark and helper words
            clean_q = re.sub(r"^(what|how|why|where|when|is|are|does|do)\s+", "", subq, flags=re.I)
            clean_q = clean_q.rstrip("?").strip()
            if clean_q.lower() not in executed_queries:
                candidates.append(clean_q)
                if len(candidates) >= limit:
                    break
        return candidates

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

