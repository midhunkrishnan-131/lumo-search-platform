"""Local Ollama adapter for offline AI Search, Chat, Streaming, and Task execution."""

from __future__ import annotations

from collections.abc import Iterator
import json
import threading
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.base import (
    AIProviderError,
    AIProviderResponse,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    BaseAIProvider,
)
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ai.ollama")

# Bound concurrent local inference to protect 8GB VRAM / 16GB RAM on local hardware
_INFERENCE_SEMAPHORE = threading.Semaphore(1)


def _validate_ollama_url(raw_url: str) -> str:
    cleaned = (raw_url or "http://localhost:11434").strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid OLLAMA_BASE_URL.")
    return cleaned


def _infer_capabilities(name: str) -> list[str]:
    low = name.lower()
    caps = ["chat", "summarization", "rag"]
    if any(k in low for k in ("coder", "code", "deepseek", "qwen")):
        caps.append("code")
    if any(k in low for k in ("instruct", "llama", "mistral", "gemma", "phi")):
        caps.append("extraction")
    return caps


class OllamaProvider(BaseAIProvider):
    """Integrates with locally hosted Ollama instances via HTTP."""

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(name="ollama")
        settings = get_settings()
        self.base_url = _validate_ollama_url(base_url or settings.ollama_base_url)
        self.default_model = (default_model or settings.ollama_model or "llama3").strip()
        self.timeout = timeout or settings.ai_request_timeout
        self.enabled = enabled if enabled is not None else settings.ollama_enabled

    def is_configured(self) -> bool:
        return self.enabled

    def check_health(self, timeout: float = 2.0) -> dict[str, Any]:
        """Check whether the local Ollama server is reachable and count installed models."""
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{self.base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                return {
                    "reachable": True,
                    "base_url": self.base_url,
                    "models_count": len(models),
                    "default_model": self.default_model,
                }
        except Exception as exc:
            logger.debug("Ollama health check failed: %s", exc)

        return {
            "reachable": False,
            "base_url": self.base_url,
            "models_count": 0,
            "default_model": self.default_model,
        }

    def list_models(self, timeout: float = 3.0) -> list[dict[str, Any]]:
        """Discover locally installed Ollama models without downloading anything."""
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{self.base_url}/api/tags")
            if resp.status_code != 200:
                raise AIProviderUnavailableError(
                    f"Ollama returned HTTP {resp.status_code} when listing models.",
                    provider="ollama",
                )
            data = resp.json()
        except httpx.RequestError as exc:
            raise AIProviderUnavailableError(
                f"Local Ollama server is not reachable at {self.base_url}.",
                provider="ollama",
            ) from exc

        models_out: list[dict[str, Any]] = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size_bytes = int(m.get("size", 0) or 0)
            details = m.get("details") or {}
            models_out.append(
                {
                    "name": name,
                    "size_bytes": size_bytes,
                    "size_gb": round(size_bytes / (1024**3), 2) if size_bytes else 0.0,
                    "family": details.get("family"),
                    "parameter_size": details.get("parameter_size"),
                    "quantization": details.get("quantization_level"),
                    "capabilities": _infer_capabilities(name),
                    "modified_at": m.get("modified_at"),
                }
            )
        return models_out

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        timeout: float | None = None,
        temperature: float = 0.2,
    ) -> AIProviderResponse:
        """Execute a bounded multi-turn chat completion against local Ollama."""
        if not self.is_configured():
            raise AIProviderUnavailableError(
                "Local Ollama provider is not enabled (OLLAMA_ENABLED=false).",
                provider="ollama",
            )

        target_model = (model or self.default_model).strip()
        effective_timeout = timeout or max(self.timeout, 60.0)
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        with _INFERENCE_SEMAPHORE:
            try:
                with httpx.Client(timeout=effective_timeout) as client:
                    resp = client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                logger.warning("Ollama request timed out after %.1fs", effective_timeout)
                raise AIProviderTimeoutError(
                    f"Ollama local instance timed out after {effective_timeout}s.",
                    provider="ollama",
                ) from exc
            except httpx.RequestError as exc:
                logger.warning("Ollama connection error: %s", exc)
                raise AIProviderUnavailableError(
                    f"Could not connect to local Ollama server at {self.base_url}.",
                    provider="ollama",
                ) from exc

        if resp.status_code != 200:
            raise AIProviderError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text}",
                provider="ollama",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AIProviderError("Malformed JSON received from Ollama.", provider="ollama") from exc

        text_content = (data.get("message") or {}).get("content", "").strip()
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        total_tokens = (
            prompt_tokens + completion_tokens
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )

        return AIProviderResponse(
            content=text_content,
            provider="ollama",
            model=target_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response=data,
        )

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        timeout: float | None = None,
        cancel_event: threading.Event | None = None,
        temperature: float = 0.2,
    ) -> Iterator[dict[str, Any]]:
        """Stream token chunks from local Ollama /api/chat with cancellation support."""
        if not self.is_configured():
            raise AIProviderUnavailableError(
                "Local Ollama provider is not enabled (OLLAMA_ENABLED=false).",
                provider="ollama",
            )

        target_model = (model or self.default_model).strip()
        effective_timeout = timeout or max(self.timeout, 90.0)
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        with _INFERENCE_SEMAPHORE:
            try:
                with httpx.Client(timeout=effective_timeout) as client:
                    with client.stream("POST", url, json=payload) as resp:
                        if resp.status_code != 200:
                            body = resp.read().decode("utf-8", errors="replace")
                            raise AIProviderError(
                                f"Ollama stream failed HTTP {resp.status_code}: {body}",
                                provider="ollama",
                                status_code=resp.status_code,
                            )
                        for line in resp.iter_lines():
                            if cancel_event is not None and cancel_event.is_set():
                                yield {"token": "", "done": True, "cancelled": True, "model": target_model}
                                return
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            token = (chunk.get("message") or {}).get("content", "")
                            done = bool(chunk.get("done", False))
                            yield {
                                "token": token,
                                "done": done,
                                "cancelled": False,
                                "model": target_model,
                            }
                            if done:
                                return
            except httpx.TimeoutException as exc:
                raise AIProviderTimeoutError(
                    f"Ollama stream timed out after {effective_timeout}s.",
                    provider="ollama",
                ) from exc
            except httpx.RequestError as exc:
                raise AIProviderUnavailableError(
                    f"Could not connect to local Ollama server at {self.base_url}.",
                    provider="ollama",
                ) from exc

    def generate_grounded_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages=messages, model=model, timeout=timeout, temperature=0.2)
