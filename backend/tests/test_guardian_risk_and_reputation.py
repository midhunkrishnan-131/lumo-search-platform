"""Unit tests for Guardian deterministic risk engine, reputation provider, and AI explainer."""

from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from app.guardian.explainer import GuardianAIExplainer
from app.guardian.reputation import VirusTotalProvider
from app.guardian.risk import RiskAssessmentEngine
from app.schemas.guardian import GuardianFinding


def test_risk_engine_low_risk_for_clean_target():
    engine = RiskAssessmentEngine()
    findings = [
        GuardianFinding(
            name="Normal Web Page",
            description="Informational note",
            severity="informational",
            evidence="HTTPS 200 OK",
            recommendation="",
        )
    ]
    risk_level, score, recs, limits = engine.evaluate(findings)

    assert risk_level == "Low"
    assert score == 0
    assert any("No active indicators of compromise" in r for r in recs)
    assert len(limits) > 0


def test_risk_engine_critical_for_blocked_or_mismatch():
    engine = RiskAssessmentEngine()
    findings = [
        GuardianFinding(
            name="File Extension and Magic Signature Mismatch",
            description="PE executable disguised as PDF",
            severity="critical",
            evidence="Extension .pdf vs Signature PE",
            recommendation="Do not open.",
        )
    ]
    risk_level, score, recs, limits = engine.evaluate(findings)

    assert risk_level == "Critical"
    assert score >= 90
    assert "Do not open." in recs


def test_risk_engine_incorporates_reputation_flags():
    engine = RiskAssessmentEngine()
    findings = []
    reputation = {
        "status": "completed",
        "malicious_count": 8,
        "suspicious_count": 2,
    }
    risk_level, score, recs, _ = engine.evaluate(findings, reputation=reputation)

    assert risk_level == "Critical"
    assert score >= 75
    assert any("Block this target immediately" in r for r in recs)


def test_virustotal_provider_unconfigured():
    provider = VirusTotalProvider()
    provider.settings.guardian_virustotal_api_key = ""

    assert provider.is_configured() is False
    res_url = provider.lookup_url("https://example.com")
    assert res_url["configured"] is False
    assert res_url["status"] == "unconfigured"

    res_file = provider.lookup_file_hash("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert res_file["configured"] is False
    assert res_file["status"] == "unconfigured"


def test_virustotal_provider_handles_rate_limit():
    provider = VirusTotalProvider()
    provider.settings.guardian_virustotal_api_key = "mock-key"

    err_429 = urllib.error.HTTPError(
        url="https://virustotal.com",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=err_429):
        res = provider.lookup_url("https://example.com")
        assert res["status"] == "rate_limited"
        assert "rate limit reached" in res["note"]


def test_ai_explainer_generates_explanation():
    mock_router = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "This URL was flagged as Critical because it impersonates PayPal on an untrusted domain."
    mock_router.execute.return_value = (mock_response, False, "gemini")

    explainer = GuardianAIExplainer(router=mock_router)
    findings = [
        GuardianFinding(
            name="Brand Keyword in Subdomain",
            description="Keyword paypal in untrusted domain",
            severity="high",
            evidence="Host: paypal.evil.com",
            recommendation="Do not enter credentials.",
        )
    ]
    explanation = explainer.explain(
        target="https://paypal.evil.com",
        target_type="URL",
        risk_level="High",
        risk_score=50,
        findings=findings,
    )

    assert explanation is not None
    assert "Critical" in explanation or "PayPal" in explanation
    assert mock_router.execute.call_count == 1
