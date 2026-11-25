"""Guardian AI Explainer: Plain-English contextual explanations of deterministic security findings."""

from __future__ import annotations

from typing import Any

from app.ai.router import AIProviderRouter, ai_provider_router
from app.core.logging import get_logger
from app.schemas.guardian import GuardianFinding

logger = get_logger("guardian.explainer")

EXPLAINER_SYSTEM_PROMPT = """You are the LUMO Download Guardian Security Explainer.
Your role is to explain pre-computed static security findings, risk levels, and recommendations in clear, actionable plain English.

CRITICAL SAFETY GUIDELINES:
1. You are strictly an EXPLAINER of already-detected findings. You are NOT an authoritative detector.
2. NEVER override or contradict the deterministic risk classification or score.
3. NEVER label any file, URL, or domain as "safe", "clean", or "guaranteed harmless".
4. NEVER fabricate CVE numbers, malware family names, or threat intelligence that is not in the findings.
5. Emphasize defensive precautions and explain the mechanics of why the detected indicators matter.
"""


class GuardianAIExplainer:
    """Interprets deterministic security findings using LUMO's AI Provider Router."""

    def __init__(self, router: AIProviderRouter | None = None) -> None:
        self.router = router or ai_provider_router

    def explain(
        self,
        target: str,
        target_type: str,
        risk_level: str,
        risk_score: int,
        findings: list[GuardianFinding],
        reputation: dict[str, Any] | None = None,
        provider: str = "auto",
    ) -> str | None:
        """Generate a concise plain-English explanation of the security findings."""
        if not findings and risk_score == 0:
            return (
                f"LUMO Guardian inspected {target_type} '{target}'. "
                f"No suspicious static indicators or policy violations were detected by the checks performed. "
                f"The target was assigned a {risk_level} Risk rating ({risk_score}/100). "
                f"Remember that static inspection cannot detect all threats; always confirm source authenticity."
            )

        findings_summary = "\n".join(
            f"- [{f.severity.upper()}] {f.name}: {f.description} (Evidence: {f.evidence})"
            for f in findings
        )

        user_prompt = f"""Target ({target_type}): {target}
Assigned Risk Level: {risk_level} (Score: {risk_score}/100)

Detected Findings:
{findings_summary}

Reputation Intelligence:
{reputation.get('note', '') if reputation else 'None'}

Please explain these findings clearly for a user, explaining what risks they present and what precautions should be taken."""

        try:
            resp, _, active_provider = self.router.execute(
                system_prompt=EXPLAINER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                requested_provider=provider,
            )
            return resp.content.strip()
        except Exception as exc:
            logger.debug("AI explanation generation skipped/failed: %s", exc)
            return None


guardian_explainer = GuardianAIExplainer()
