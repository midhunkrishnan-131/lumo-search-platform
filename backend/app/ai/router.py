"""Central AI Provider Router coordinating primary provider selection, retries, circuit breakers, and fallback."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.ai.base import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderResponse,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    BaseAIProvider,
)
from app.ai.gemini import GeminiProvider
from app.ai.grok import GrokProvider
from app.ai.ollama import OllamaProvider
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ai.router")

_TRANSIENT_ERRORS = (
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)


class AIProviderRouter:
    """Manages AI provider adapters, timeouts, bounded retries, circuit breakers, and fallback."""

    def __init__(
        self,
        providers: dict[str, BaseAIProvider] | None = None,
        primary_provider: str | None = None,
        fallback_provider: str | None = None,
        local_only_mode: bool | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
        circuit_breaker_threshold: int | None = None,
        circuit_breaker_cooldown_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.providers: dict[str, BaseAIProvider] = providers or {
            "gemini": GeminiProvider(),
            "grok": GrokProvider(),
            "ollama": OllamaProvider(),
        }
        self.primary_provider = (primary_provider or settings.ai_primary_provider or "gemini").lower().strip()
        self.fallback_provider = (fallback_provider or settings.ai_fallback_provider or "").lower().strip()
        self.local_only_mode = (
            local_only_mode if local_only_mode is not None else settings.local_only_ai
        )
        self.max_retries = max(0, settings.ai_max_retries if max_retries is None else max_retries)
        self.retry_backoff_seconds = max(
            0.0,
            settings.ai_retry_backoff_seconds if retry_backoff_seconds is None else retry_backoff_seconds,
        )
        self.cb_threshold = max(
            1,
            settings.ai_circuit_breaker_threshold if circuit_breaker_threshold is None else circuit_breaker_threshold,
        )
        self.cb_cooldown = max(
            1.0,
            settings.ai_circuit_breaker_cooldown_seconds
            if circuit_breaker_cooldown_seconds is None
            else circuit_breaker_cooldown_seconds,
        )
        self._cb_lock = threading.Lock()
        self._cb_state: dict[str, dict[str, Any]] = {}

    def _get_cb(self, name: str) -> dict[str, Any]:
        entry = self._cb_state.get(name)
        if entry is None:
            entry = {
                "consecutive_failures": 0,
                "opened_until": 0.0,
                "last_error_class": None,
                "total_successes": 0,
                "total_failures": 0,
            }
            self._cb_state[name] = entry
        return entry

    def _is_circuit_open(self, name: str) -> bool:
        with self._cb_lock:
            entry = self._get_cb(name)
            return entry["opened_until"] > time.monotonic()

    def _record_success(self, name: str) -> None:
        with self._cb_lock:
            entry = self._get_cb(name)
            entry["consecutive_failures"] = 0
            entry["opened_until"] = 0.0
            entry["total_successes"] += 1

    def _record_failure(self, name: str, exc: Exception) -> None:
        with self._cb_lock:
            entry = self._get_cb(name)
            entry["consecutive_failures"] += 1
            entry["total_failures"] += 1
            entry["last_error_class"] = type(exc).__name__
            if entry["consecutive_failures"] >= self.cb_threshold:
                entry["opened_until"] = time.monotonic() + self.cb_cooldown
                logger.warning(
                    "Circuit breaker opened for provider '%s' for %.0fs after %d consecutive failures",
                    name,
                    self.cb_cooldown,
                    entry["consecutive_failures"],
                )

    def _call_with_resilience(
        self,
        name: str,
        provider: BaseAIProvider,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        if self._is_circuit_open(name):
            raise AIProviderUnavailableError(
                f"Provider '{name}' circuit breaker is open due to recent failures.",
                provider=name,
            )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = provider.generate_grounded_answer(
                    system_prompt, user_prompt, model=model, timeout=timeout
                )
                self._record_success(name)
                return resp
            except AIProviderAuthError as auth_exc:
                # Never retry auth failures
                self._record_failure(name, auth_exc)
                raise
            except _TRANSIENT_ERRORS as t_exc:
                last_exc = t_exc
                self._record_failure(name, t_exc)
                if attempt < self.max_retries and not self._is_circuit_open(name):
                    delay = self.retry_backoff_seconds * (2 ** attempt)
                    if delay > 0:
                        time.sleep(min(delay, 5.0))
                    continue
                raise
            except Exception as exc:
                self._record_failure(name, exc)
                raise

        assert last_exc is not None
        raise last_exc

    def get_provider(self, name: str) -> BaseAIProvider:
        key = name.lower().strip()
        if key not in self.providers:
            raise AIProviderError(f"Unknown AI provider '{name}'. Supported: {list(self.providers.keys())}", provider=name)
        return self.providers[key]

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status of configured providers and circuit breakers without leaking credentials."""
        now = time.monotonic()
        status_info: dict[str, Any] = {
            "primary": self.primary_provider,
            "fallback": None if self.local_only_mode else (self.fallback_provider or None),
            "local_only_mode": self.local_only_mode,
            "providers": {},
        }
        with self._cb_lock:
            for name, provider in self.providers.items():
                cb = self._get_cb(name)
                is_open = cb["opened_until"] > now
                status_info["providers"][name] = {
                    "configured": provider.is_configured(),
                    "blocked_by_privacy_mode": self.local_only_mode and name != "ollama",
                    "circuit_state": "open" if is_open else "closed",
                    "consecutive_failures": cb["consecutive_failures"],
                    "total_successes": cb["total_successes"],
                    "total_failures": cb["total_failures"],
                    "last_error_class": cb["last_error_class"],
                }
        return status_info

    def execute(
        self,
        system_prompt: str,
        user_prompt: str,
        requested_provider: str = "auto",
        model: str | None = None,
        timeout: float | None = None,
    ) -> tuple[AIProviderResponse, bool, str]:
        """Execute grounded generation using requested or primary provider with bounded retry and fallback."""
        req = requested_provider.lower().strip()

        # Local-Only Privacy Mode enforcement: never route or fall back to external AI providers
        if self.local_only_mode:
            if req and req not in ("auto", "ollama"):
                raise AIProviderError(
                    f"External provider '{req}' is blocked while Local-Only Privacy Mode is active.",
                    provider=req,
                )
            ollama = self.get_provider("ollama")
            logger.info("Local-Only Privacy Mode active: routing strictly to local Ollama")
            response = self._call_with_resilience("ollama", ollama, system_prompt, user_prompt, model=model, timeout=timeout)
            return response, False, "ollama"

        # Direct explicit provider selection
        if req and req != "auto":
            provider = self.get_provider(req)
            logger.info("Executing generation using explicitly requested provider '%s'", req)
            response = self._call_with_resilience(req, provider, system_prompt, user_prompt, model=model, timeout=timeout)
            return response, False, req

        # Automatic provider selection (Primary -> Optional Fallback)
        primary_name = self.primary_provider
        fallback_name = self.fallback_provider
        primary = self.get_provider(primary_name)

        try:
            logger.info("Executing generation with primary provider '%s'", primary_name)
            response = self._call_with_resilience(primary_name, primary, system_prompt, user_prompt, model=model, timeout=timeout)
            return response, False, primary_name
        except (
            AIProviderRateLimitError,
            AIProviderTimeoutError,
            AIProviderUnavailableError,
            AIProviderAuthError,
        ) as primary_exc:
            logger.warning(
                "Primary provider '%s' encountered error (%s)",
                primary_name,
                type(primary_exc).__name__,
            )

            if fallback_name and fallback_name != primary_name and fallback_name in self.providers:
                fallback = self.providers[fallback_name]
                if fallback.is_configured():
                    logger.info("Initiating fallback to provider '%s'", fallback_name)
                    try:
                        fb_response = self._call_with_resilience(
                            fallback_name, fallback, system_prompt, user_prompt, timeout=timeout
                        )
                        return fb_response, True, fallback_name
                    except Exception as fb_exc:
                        logger.error(
                            "Fallback provider '%s' also failed (%s)",
                            fallback_name,
                            type(fb_exc).__name__,
                        )
                        raise primary_exc from fb_exc

            raise primary_exc


# Global router singleton
ai_provider_router = AIProviderRouter()
