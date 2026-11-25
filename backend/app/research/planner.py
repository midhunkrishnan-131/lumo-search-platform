"""Research Planner: Decomposes topics into structured objectives and initial queries."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.router import AIProviderRouter, ai_provider_router
from app.core.logging import get_logger
from app.schemas.research import ResearchPlan

logger = get_logger("research.planner")

PLANNER_SYSTEM_PROMPT = """You are the LUMO Autonomous Research Planner.
Your role is to decompose a complex research topic into a rigorous, bounded, verifiable investigation plan.

Respond strictly in valid JSON format with the following keys:
{
  "objectives": ["Clear objective 1", "Clear objective 2", "Clear objective 3"],
  "subquestions": ["Specific subquestion 1", "Specific subquestion 2", "Specific subquestion 3", "Specific subquestion 4"],
  "initial_queries": ["exact search query 1", "exact search query 2", "exact search query 3"],
  "expected_evidence": ["Expected document type 1", "Expected benchmark/fact 2"]
}

Guidelines:
- Generate 3 to 4 focused subquestions directly addressing the core inquiry.
- Generate 2 to 3 concise, specific search queries optimized for a hybrid keyword + vector search engine.
- Never include conversational text, apologies, or markdown outside the JSON object.
"""


class ResearchPlanner:
    """Generates structured research plans using AI Provider Router with deterministic fallbacks."""

    def __init__(self, router: AIProviderRouter | None = None) -> None:
        self.router = router or ai_provider_router

    def create_plan(self, topic: str, provider: str = "auto") -> ResearchPlan:
        """Decompose topic into a validated ResearchPlan."""
        clean_topic = topic[:300].strip()
        if not clean_topic:
            return self._fallback_plan("General Research Topic")

        user_prompt = f"Decompose this research topic into a structured investigation plan: {clean_topic}"

        try:
            resp, _, _ = self.router.execute(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                requested_provider=provider,
            )
            parsed = self._parse_json(resp.content)
            if parsed and isinstance(parsed, dict) and "subquestions" in parsed:
                return ResearchPlan(
                    topic=clean_topic,
                    objectives=parsed.get("objectives", [f"Investigate {clean_topic}"]),
                    subquestions=parsed.get("subquestions", [f"What are the core mechanisms of {clean_topic}?"]),
                    initial_queries=parsed.get("initial_queries", [clean_topic]),
                    expected_evidence=parsed.get("expected_evidence", ["Indexed technical documentation"]),
                )
        except Exception as exc:
            logger.warning("AI planner failed (%s), using deterministic fallback plan", exc)

        return self._fallback_plan(clean_topic)

    def _fallback_plan(self, topic: str) -> ResearchPlan:
        """Deterministic plan if AI provider is unavailable or returns invalid JSON."""
        # Extract meaningful keywords
        words = [w for w in re.findall(r"\b\w{3,}\b", topic) if w.lower() not in {"how", "what", "why", "the", "and", "for"}]
        kw1 = words[0] if words else "system"
        kw2 = words[1] if len(words) > 1 else "architecture"

        return ResearchPlan(
            topic=topic,
            objectives=[
                f"Analyze core definitions and architecture of {topic}",
                f"Evaluate trade-offs, performance, and implementation characteristics of {topic}",
                f"Identify empirical evidence, contradictions, and information gaps",
            ],
            subquestions=[
                f"How is {topic} fundamentally designed and implemented?",
                f"What are the primary operational characteristics and trade-offs of {kw1}?",
                f"Where do benchmark findings or technical analyses disagree regarding {kw2}?",
                f"What limitations or constraints are noted in practice?",
            ],
            initial_queries=[
                topic,
                f"{kw1} architecture overview",
                f"{kw1} {kw2} trade-offs",
            ],
            expected_evidence=[
                "Architecture specifications and guides",
                "Benchmark and performance analyses",
            ],
        )

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        """Clean markdown fences and parse JSON safely."""
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            # Try to match the first JSON object inside the text
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

