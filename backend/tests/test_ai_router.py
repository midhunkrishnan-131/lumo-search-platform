"""Unit tests for AI Provider Router and fallback execution."""

import pytest
from app.ai.base import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderResponse,
    BaseAIProvider,
)
from app.ai.router import AIProviderRouter


class DummyProvider(BaseAIProvider):
    def __init__(self, name: str, configured: bool = True, fail_with: Exception | None = None) -> None:
        super().__init__(name=name)
        self.configured = configured
        self.fail_with = fail_with
        self.called_count = 0

    def is_configured(self) -> bool:
        return self.configured

    def generate_grounded_answer(self, system_prompt: str, user_prompt: str, model=None, timeout=None) -> AIProviderResponse:
        self.called_count += 1
        if self.fail_with:
            raise self.fail_with
        return AIProviderResponse(
            content=f"Response from {self.name}",
            provider=self.name,
            model=model or f"{self.name}-default",
        )


def test_router_explicit_provider():
    p1 = DummyProvider("gemini")
    p2 = DummyProvider("grok")
    router = AIProviderRouter(providers={"gemini": p1, "grok": p2}, primary_provider="gemini")

    resp, fb_used, prov = router.execute("sys", "user", requested_provider="grok")
    assert prov == "grok"
    assert fb_used is False
    assert resp.content == "Response from grok"
    assert p1.called_count == 0
    assert p2.called_count == 1


def test_router_unknown_provider():
    router = AIProviderRouter(providers={"gemini": DummyProvider("gemini")})
    with pytest.raises(AIProviderError) as exc_info:
        router.execute("sys", "user", requested_provider="claude")
    assert "Unknown AI provider" in str(exc_info.value)


def test_router_fallback_success():
    """Primary fails with rate limit, router successfully falls back to secondary provider."""
    primary = DummyProvider("gemini", fail_with=AIProviderRateLimitError("Rate limited", provider="gemini"))
    fallback = DummyProvider("grok")
    router = AIProviderRouter(
        providers={"gemini": primary, "grok": fallback},
        primary_provider="gemini",
        fallback_provider="grok",
    )

    resp, fb_used, prov = router.execute("sys", "user", requested_provider="auto")
    assert fb_used is True
    assert prov == "grok"
    assert resp.content == "Response from grok"
    assert primary.called_count == 1
    assert fallback.called_count == 1


def test_router_no_fallback_configured():
    """Primary fails and no fallback is set -> raises primary error."""
    primary = DummyProvider("gemini", fail_with=AIProviderRateLimitError("Quota exceeded", provider="gemini"))
    router = AIProviderRouter(
        providers={"gemini": primary},
        primary_provider="gemini",
        fallback_provider="",
    )

    with pytest.raises(AIProviderRateLimitError):
        router.execute("sys", "user", requested_provider="auto")


def test_router_status_masks_credentials():
    primary = DummyProvider("gemini", configured=True)
    fallback = DummyProvider("grok", configured=False)
    router = AIProviderRouter(
        providers={"gemini": primary, "grok": fallback},
        primary_provider="gemini",
        fallback_provider="grok",
    )

    status = router.get_status()
    assert status["primary"] == "gemini"
    assert status["fallback"] == "grok"
    assert status["providers"]["gemini"]["configured"] is True
    assert status["providers"]["grok"]["configured"] is False
    # Verify no raw keys exist
    assert "api_key" not in status
