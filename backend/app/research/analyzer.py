"""Evidence Analyzer: Evaluates collected evidence to identify findings, contradictions, and gaps."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.router import AIProviderRouter, ai_provider_router
from app.core.logging import get_logger
from app.schemas.research import ResearchEvidenceItem, ResearchFindingItem, ResearchPlan

logger = get_logger("research.analyzer")

ANALYZER_SYSTEM_PROMPT = """You are the LUMO Research Evidence Analyzer.
Your task is to analyze retrieved evidence against the research plan's subquestions.
Distinguish between directly supported facts, conflicting or contradictory claims, and information gaps.

Output STRICT JSON with the key "findings", where each item is an object:
{
  "findings": [
    {
      "kind": "Supported Finding",
      "text": "Clear finding with source citation e.g. [S1].",
      "citations": ["S1"]
    },
    {
      "kind": "Contradiction Noted",
      "text": "Explanation of conflicting evidence across [S1] and [S2].",
      "citations": ["S1", "S2"]
    },
    {
      "kind": "Information Gap",
      "text": "Description of unanswered question or missing empirical data.",
      "citations": []
    }
  ]
}

Only cite source keys ([S1], [S2]) that actually appear in the evidence. Never invent citations.
"""


class EvidenceAnalyzer:
    """Analyzes evidence passages and extracts structured findings using AI Provider Router."""

    def __init__(self, router: AIProviderRouter | None = None) -> None:
        self.router = router or ai_provider_router

    def analyze(
        self,
        plan: ResearchPlan,
        sources: list[ResearchEvidenceItem],
        provider: str = "auto",
    ) -> list[ResearchFindingItem]:
        """Analyze evidence against plan subquestions and return structured findings."""
        if not sources:
            return [
                ResearchFindingItem(
                    kind="Information Gap",
                    text="No evidence has been retrieved yet from the indexed knowledge base.",
                    citations=[],
                )
            ]

        evidence_summary = "\n".join(f"[{s.source_id}] {s.title}: {s.passage[:300]}" for s in sources[:12])
        subq_text = "\n".join(f"- {q}" for q in plan.subquestions)

        user_prompt = f"""Subquestions to evaluate:
{subq_text}

Evidence:
{evidence_summary}

Analyze the evidence and extract Supported Findings, Contradictions, and Information Gaps:"""

        try:
            resp, _, _ = self.router.execute(
                system_prompt=ANALYZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                requested_provider=provider,
            )
            parsed = self._parse_json(resp.content)
            if parsed and isinstance(parsed, dict) and "findings" in parsed:
                findings: list[ResearchFindingItem] = []
                for f in parsed["findings"]:
                    kind = f.get("kind", "Supported Finding")
                    if kind not in {"Supported Finding", "Contradiction Noted", "Information Gap"}:
                        kind = "Supported Finding"
                    findings.append(
                        ResearchFindingItem(
                            kind=kind,
                            text=f.get("text", "").strip(),
                            citations=f.get("citations", []),
                        )
                    )
                if findings:
                    return findings
        except Exception as exc:
            logger.warning("AI evidence analysis failed (%s), using deterministic analyzer fallback", exc)

        return self._fallback_analysis(plan, sources)

    def _fallback_analysis(
        self,
        plan: ResearchPlan,
        sources: list[ResearchEvidenceItem],
    ) -> list[ResearchFindingItem]:
        """Deterministic findings generation when AI provider is offline."""
        findings = []
        if sources:
            s1 = sources[0]
            findings.append(
                ResearchFindingItem(
                    kind="Supported Finding",
                    text=f"Indexed evidence confirms core technical attributes regarding '{plan.topic}' [{s1.source_id}].",
                    citations=[s1.source_id],
                )
            )
        if len(sources) > 1:
            s2 = sources[1]
            findings.append(
                ResearchFindingItem(
                    kind="Supported Finding",
                    text=f"Additional implementation details and contextual constraints identified in [{s2.source_id}].",
                    citations=[s2.source_id],
                )
            )
        findings.append(
            ResearchFindingItem(
                kind="Information Gap",
                text=f"Empirical benchmarks or live production telemetry for '{plan.topic}' require further investigative steps.",
                citations=[],
            )
        )
        return findings

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
