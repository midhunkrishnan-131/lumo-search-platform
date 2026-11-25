"""Unit tests for Gemini, Grok, and Ollama AI provider adapters."""

import pytest
import httpx
from app.ai.base import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.ai.gemini import GeminiProvider
from app.ai.grok import GrokProvider
from app.ai.ollama import OllamaProvider


# ==================== Gemini Tests ====================

def test_gemini_unconfigured():
    provider = GeminiProvider(api_key="")
    assert provider.is_configured() is False
    with pytest.raises(AIProviderAuthError):
        provider.generate_grounded_answer("system", "user")


def test_gemini_success(monkeypatch):
    provider = GeminiProvider(api_key="test-gemini-key", default_model="gemini-1.5-flash")
    assert provider.is_configured() is True

    fake_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Grounded answer from Gemini [S1]."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 25,
            "totalTokenCount": 145,
        },
    }

    def mock_post(*args, **kwargs):
        # Verify API key is passed in params, not URL path
        params = kwargs.get("params", {})
        assert params.get("key") == "test-gemini-key"
        return httpx.Response(200, json=fake_response_data, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = provider.generate_grounded_answer("System instruction", "User question")
    assert res.provider == "gemini"
    assert res.content == "Grounded answer from Gemini [S1]."
    assert res.prompt_tokens == 120
    assert res.completion_tokens == 25
    assert res.total_tokens == 145


def test_gemini_rate_limit(monkeypatch):
    provider = GeminiProvider(api_key="test-key")

    def mock_post(*args, **kwargs):
        return httpx.Response(429, json={"error": "Rate limit"}, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIProviderRateLimitError) as exc_info:
        provider.generate_grounded_answer("system", "user")
    assert exc_info.value.status_code == 429


def test_gemini_auth_error(monkeypatch):
    provider = GeminiProvider(api_key="invalid-key")

    def mock_post(*args, **kwargs):
        return httpx.Response(400, json={"error": {"message": "API_KEY_INVALID"}}, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIProviderAuthError):
        provider.generate_grounded_answer("system", "user")


def test_gemini_timeout(monkeypatch):
    provider = GeminiProvider(api_key="test-key")

    def mock_post(*args, **kwargs):
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIProviderTimeoutError):
        provider.generate_grounded_answer("system", "user")


# ==================== Grok Tests ====================

def test_grok_unconfigured():
    provider = GrokProvider(api_key="")
    assert provider.is_configured() is False
    with pytest.raises(AIProviderAuthError):
        provider.generate_grounded_answer("system", "user")


def test_grok_success(monkeypatch):
    provider = GrokProvider(api_key="xai-test-key", default_model="grok-beta")
    assert provider.is_configured() is True

    fake_response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Answer from Grok [S2]."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 15, "total_tokens": 95},
    }

    def mock_post(*args, **kwargs):
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer xai-test-key"
        return httpx.Response(200, json=fake_response, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = provider.generate_grounded_answer("system", "user")
    assert res.provider == "grok"
    assert res.content == "Answer from Grok [S2]."
    assert res.total_tokens == 95


def test_grok_rate_limit(monkeypatch):
    provider = GrokProvider(api_key="xai-test-key")

    def mock_post(*args, **kwargs):
        return httpx.Response(429, json={"error": "Rate limit"}, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIProviderRateLimitError):
        provider.generate_grounded_answer("system", "user")


# ==================== Ollama Tests ====================

def test_ollama_disabled():
    provider = OllamaProvider(enabled=False)
    assert provider.is_configured() is False
    with pytest.raises(AIProviderUnavailableError):
        provider.generate_grounded_answer("system", "user")


def test_ollama_success(monkeypatch):
    provider = OllamaProvider(enabled=True, base_url="http://localhost:11434", default_model="llama3")
    assert provider.is_configured() is True

    fake_response = {
        "message": {"role": "assistant", "content": "Answer from Ollama local [S1]."},
        "prompt_eval_count": 50,
        "eval_count": 20,
    }

    def mock_post(*args, **kwargs):
        return httpx.Response(200, json=fake_response, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = provider.generate_grounded_answer("system", "user")
    assert res.provider == "ollama"
    assert res.content == "Answer from Ollama local [S1]."
    assert res.total_tokens == 70
