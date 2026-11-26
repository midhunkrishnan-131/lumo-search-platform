"""Google Gemini REST API adapter for grounded AI Search answer generation."""

from __future__ import annotations

import json
import time
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

logger = get_logger("ai.gemini")

GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(BaseAIProvider):
    """Integrates with Google Gemini via official HTTPS REST endpoints using httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(name="gemini")
        settings = get_settings()
        self.api_key = (api_key if api_key is not None else settings.gemini_api_key).strip()
        self.default_model = (default_model or settings.gemini_model or "gemini-3.5-flash-lite").strip()
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
            raise AIProviderAuthError("Gemini API key is not configured.", provider="gemini")

        target_model = (model or self.default_model).strip()
        effective_timeout = timeout or self.timeout

        # Structure payload following Google Generative Language REST API spec
        url = GEMINI_API_URL_TEMPLATE.format(model=target_model)
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload: dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        # Retry on 503 (high demand / transient overload) with exponential backoff
        _max_retries = 2
        _last_exc: Exception | None = None
        resp = None
        for _attempt in range(_max_retries + 1):
            try:
                with httpx.Client(timeout=effective_timeout) as client:
                    resp = client.post(url, headers=headers, params=params, json=payload)
                if resp.status_code != 503:
                    break  # Success or non-retriable error
                wait = 2 ** _attempt  # 1s, 2s, 4s
                logger.warning(
                    "Gemini HTTP 503 (attempt %d/%d), retrying in %ds…",
                    _attempt + 1, _max_retries + 1, wait,
                )
                time.sleep(wait)
            except httpx.TimeoutException as exc:
                logger.warning("Gemini request timed out after %.1fs", effective_timeout)
                raise AIProviderTimeoutError(
                    f"Gemini API request timed out after {effective_timeout}s.",
                    provider="gemini",
                ) from exc
            except httpx.RequestError as exc:
                _last_exc = exc
                logger.warning("Gemini network request error (%s)", type(exc).__name__)
                if _attempt < _max_retries:
                    time.sleep(2 ** _attempt)
                    continue
                raise AIProviderUnavailableError(
                    "Gemini API service is currently unreachable.",
                    provider="gemini",
                ) from exc

        if resp is None:
            raise AIProviderUnavailableError(
                "Gemini API service is currently unreachable.",
                provider="gemini",
            )

        if resp.status_code == 429:
            logger.warning("Gemini rate limit exceeded (HTTP 429)")
            raise AIProviderRateLimitError(
                "Gemini API rate limit exceeded. Please try again shortly.",
                provider="gemini",
                status_code=429,
            )
        elif resp.status_code in (401, 403):
            logger.warning("Gemini authentication failure (HTTP %d)", resp.status_code)
            raise AIProviderAuthError(
                "Gemini API key authentication failed.",
                provider="gemini",
                status_code=resp.status_code,
            )
        elif resp.status_code == 400:
            error_data = {}
            try:
                error_data = resp.json().get("error", {})
            except Exception:
                pass
            message = error_data.get("message", "Bad request.")
            if "API_KEY_INVALID" in message or "API key not valid" in message:
                raise AIProviderAuthError("Invalid Gemini API key.", provider="gemini", status_code=400)
            raise AIProviderError(f"Gemini API request error: {message}", provider="gemini", status_code=400)
        elif resp.status_code == 404:
            raise AIProviderError(
                f"Gemini model '{target_model}' was not found (HTTP 404).",
                provider="gemini",
                status_code=404,
            )
        elif resp.status_code >= 500:
            raise AIProviderUnavailableError(
                f"Gemini API server returned HTTP {resp.status_code}.",
                provider="gemini",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AIProviderError("Malformed JSON received from Gemini API.", provider="gemini") from exc

        # Parse text candidate
        candidates = data.get("candidates", [])
        if not candidates:
            raise AIProviderError("Gemini returned no response candidates.", provider="gemini")

        candidate = candidates[0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])
        text_content = "".join(p.get("text", "") for p in parts if "text" in p).strip()

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount")
        completion_tokens = usage.get("candidatesTokenCount")
        total_tokens = usage.get("totalTokenCount")

        return AIProviderResponse(
            content=text_content,
            provider="gemini",
            model=target_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response=data,
        )
