"""xAI Grok API adapter for grounded AI Search answer generation."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.base import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderResponse,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    BaseAIProvider,
)
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ai.grok")

GROK_API_URL = "https://api.x.ai/v1/chat/completions"


class GrokProvider(BaseAIProvider):
    """Integrates with xAI Grok API using OpenAI-compatible HTTPS chat endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(name="grok")
        settings = get_settings()
        self.api_key = (api_key if api_key is not None else settings.grok_api_key).strip()
        self.default_model = (default_model or settings.grok_model or "grok-beta").strip()
        self.timeout = timeout or settings.ai_request_timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_grounded_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        if not self.is_configured():
            raise AIProviderAuthError("Grok API key is not configured.", provider="grok")

        target_model = (model or self.default_model).strip()
        effective_timeout = timeout or self.timeout

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=effective_timeout) as client:
                resp = client.post(GROK_API_URL, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("Grok request timed out after %.1fs", effective_timeout)
            raise AIProviderTimeoutError(
                f"Grok API request timed out after {effective_timeout}s.",
                provider="grok",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Grok network request error: %s", exc)
            raise AIProviderUnavailableError(
                "Grok API service is currently unreachable.",
                provider="grok",
            ) from exc

        if resp.status_code == 429:
            raise AIProviderRateLimitError(
                "Grok API rate limit exceeded.",
                provider="grok",
                status_code=429,
            )
        elif resp.status_code in (401, 403):
            raise AIProviderAuthError(
                "Grok API authentication failed. Check GROK_API_KEY.",
                provider="grok",
                status_code=resp.status_code,
            )
        elif resp.status_code >= 500:
            raise AIProviderUnavailableError(
                f"Grok API returned HTTP {resp.status_code}.",
                provider="grok",
                status_code=resp.status_code,
            )
        elif resp.status_code != 200:
            raise AIProviderError(
                f"Grok API returned HTTP {resp.status_code}: {resp.text}",
                provider="grok",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AIProviderError("Malformed JSON received from Grok API.", provider="grok") from exc

        choices = data.get("choices", [])
        if not choices:
            raise AIProviderError("Grok returned no completion choices.", provider="grok")

        message = choices[0].get("message", {})
        text_content = message.get("content", "").strip()

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        return AIProviderResponse(
            content=text_content,
            provider="grok",
            model=target_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response=data,
        )
