"""Base interfaces and data structures for AI providers in LUMO."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AIProviderError(Exception):
    """Base exception for AI provider failures."""

    def __init__(self, message: str, provider: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class AIProviderAuthError(AIProviderError):
    """Raised when authentication / API key is missing or invalid."""


class AIProviderRateLimitError(AIProviderError):
    """Raised when provider returns a rate limit (HTTP 429)."""


class AIProviderTimeoutError(AIProviderError):
    """Raised when provider call times out."""


class AIProviderUnavailableError(AIProviderError):
    """Raised when provider service is unreachable or returns 503."""


@dataclass
class AIProviderResponse:
    """Standardized response from an AI provider."""

    content: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class BaseAIProvider(ABC):
    """Common abstraction interface for all AI model providers."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and prerequisites are present."""
        pass

    @abstractmethod
    def generate_grounded_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        """Generate a grounded response using the provider.

        Args:
            system_prompt: Strict system prompt with instructions and boundaries.
            user_prompt: Grounded context and user query.
            model: Optional override model name.
            timeout: Optional override request timeout.

        Returns:
            AIProviderResponse dataclass with text and metadata.
        """
        pass
