"""Guardian Risk Assessment Engine: Deterministic, evidence-based scoring and classification."""

from __future__ import annotations

from typing import Any

from app.schemas.guardian import GuardianFinding

SEVERITY_WEIGHTS = {
    "critical": 90,
    "high": 50,
    "medium": 25,
    "low": 10,
    "informational": 0,
}

DEFAULT_LIMITATIONS = [
    "Analysis is strictly static and non-intrusive; executable code, macros, and scripts are not executed in a sandbox.",
    "A Low Risk finding indicates no suspicious patterns were detected by the performed checks; it is not an absolute guarantee of safety.",
    "Encrypted archives, password-protected files, and memory-only payloads cannot be inspected without keys or runtime execution.",
    "Domain reputation is based on known historical reports and may not reflect newly registered or zero-day infrastructure.",
]


class RiskAssessmentEngine:
    """Calculates deterministic risk scores, assigns risk levels, and generates defensive recommendations."""

    def evaluate(
        self,
        findings: list[GuardianFinding],
        reputation: dict[str, Any] | None = None,
        is_blocked: bool = False,
        is_unreachable: bool = False,
    ) -> tuple[str, int, list[str], list[str]]:
        """Compute (risk_level, risk_score, recommendations, limitations)."""
        score = 0
        recs: list[str] = []
        limitations: list[str] = list(DEFAULT_LIMITATIONS)

        if is_blocked:
            return (
                "Critical",
                100,
                ["Do not attempt to access this target. It violates internal security or SSRF boundaries."],
                limitations,
            )

        # 1. Sum deterministic finding severities
        for f in findings:
            weight = SEVERITY_WEIGHTS.get(f.severity.lower(), 0)
            score += weight
            if f.recommendation and f.recommendation not in recs:
                recs.append(f.recommendation)

        # 2. Add external reputation findings if available
        if reputation and reputation.get("status") == "completed":
            mal_count = reputation.get("malicious_count", 0)
            susp_count = reputation.get("suspicious_count", 0)

            if mal_count >= 5:
                score += 85
                findings.append(
                    GuardianFinding(
                        name="Multiple Security Vendors Classify as Malicious",
                        description=f"{mal_count} security engines on VirusTotal flagged this target as malicious.",
                        severity="critical",
                        evidence=f"Malicious engines: {mal_count}",
                        recommendation="Block this target immediately. It is recognized as active malware or phishing.",
                    )
                )
                recs.insert(0, "Block this target immediately. Multiple external threat intelligence vendors identify it as harmful.")
            elif mal_count >= 1:
                score += 45
                findings.append(
                    GuardianFinding(
                        name="Security Vendor Threat Intelligence Match",
                        description=f"{mal_count} security engine flagged this target as malicious.",
                        severity="high",
                        evidence=f"Malicious engines: {mal_count}",
                        recommendation="Exercise extreme caution; at least one threat engine flagged this target.",
                    )
                )
                recs.insert(0, "Exercise extreme caution; flagged as malicious by threat intelligence.")
            elif susp_count >= 1:
                score += 20
                findings.append(
                    GuardianFinding(
                        name="Suspicious Vendor Threat Intelligence Flags",
                        description=f"{susp_count} security engines flagged this target as suspicious.",
                        severity="medium",
                        evidence=f"Suspicious engines: {susp_count}",
                        recommendation="Review the source and avoid running unverified files.",
                    )
                )

        # Cap score between 0 and 100
        score = max(0, min(100, score))

        # 3. Classify Risk Level
        if is_unreachable and score == 0:
            risk_level = "Unknown"
            recs.append("Could not reach destination to verify server status. Verify network connectivity.")
        elif score >= 75:
            risk_level = "Critical"
        elif score >= 40:
            risk_level = "High"
        elif score >= 15:
            risk_level = "Medium"
        else:
            risk_level = "Low"
            recs.append("No active indicators of compromise were detected by the static rules performed.")

        if not recs:
            recs.append("Always verify file provenance and verify digital signatures before execution.")

        return risk_level, score, recs, limitations


risk_engine = RiskAssessmentEngine()
