"""Central AI Provider Router coordinating primary provider selection and resilient fallback."""

from __future__ import annotations

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


class AIProviderRouter:
    """Manages AI provider adapters, selection, timeouts, rate limits, and fallback execution."""

    def __init__(
        self,
        providers: dict[str, BaseAIProvider] | None = None,
        primary_provider: str | None = None,
        fallback_provider: str | None = None,
        local_only_mode: bool | None = None,
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

    def get_provider(self, name: str) -> BaseAIProvider:
        key = name.lower().strip()
        if key not in self.providers:
            raise AIProviderError(f"Unknown AI provider '{name}'. Supported: {list(self.providers.keys())}", provider=name)
        return self.providers[key]

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status of configured providers without leaking API credentials."""
        status_info = {
            "primary": self.primary_provider,
            "fallback": None if self.local_only_mode else (self.fallback_provider or None),
            "local_only_mode": self.local_only_mode,
            "providers": {},
        }
        for name, provider in self.providers.items():
            status_info["providers"][name] = {
                "configured": provider.is_configured(),
                "blocked_by_privacy_mode": self.local_only_mode and name != "ollama",
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
        """Execute grounded generation using requested or primary provider with graceful fallback.

        Args:
            system_prompt: Strict system prompt.
            user_prompt: Context and user question.
            requested_provider: 'auto', 'gemini', 'grok', or 'ollama'.
            model: Optional model override.
            timeout: Optional timeout override.

        Returns:
            Tuple of (AIProviderResponse, fallback_used_bool, active_provider_name)
        """
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
            response = ollama.generate_grounded_answer(
                system_prompt, user_prompt, model=model, timeout=timeout
            )
            return response, False, "ollama"

        # Direct explicit provider selection
        if req and req != "auto":
            provider = self.get_provider(req)
            logger.info("Executing generation using explicitly requested provider '%s'", req)
            response = provider.generate_grounded_answer(system_prompt, user_prompt, model=model, timeout=timeout)
            return response, False, req

        # Automatic provider selection (Primary -> Optional Fallback)
        primary_name = self.primary_provider
        fallback_name = self.fallback_provider
        primary = self.get_provider(primary_name)

        try:
            logger.info("Executing generation with primary provider '%s'", primary_name)
            response = primary.generate_grounded_answer(system_prompt, user_prompt, model=model, timeout=timeout)
            return response, False, primary_name
        except (
            AIProviderRateLimitError,
            AIProviderTimeoutError,
            AIProviderUnavailableError,
            AIProviderAuthError,
        ) as primary_exc:
            logger.warning(
                "Primary provider '%s' encountered error: %s",
                primary_name,
                primary_exc,
            )

            # Check if fallback is enabled and configured
            if fallback_name and fallback_name != primary_name and fallback_name in self.providers:
                fallback = self.providers[fallback_name]
                if fallback.is_configured():
                    logger.info("Initiating fallback to provider '%s'", fallback_name)
                    try:
                        fb_response = fallback.generate_grounded_answer(
                            system_prompt, user_prompt, timeout=timeout
                        )
                        return fb_response, True, fallback_name
                    except Exception as fb_exc:
                        logger.error(
                            "Fallback provider '%s' also failed: %s",
                            fallback_name,
                            fb_exc,
                        )
                        # Raise primary exception with note
                        raise primary_exc from fb_exc

            # If no fallback configured or possible, re-raise primary error
            raise primary_exc


# Global router singleton
ai_provider_router = AIProviderRouter()
