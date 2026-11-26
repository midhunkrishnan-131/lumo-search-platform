# LUMO Provider Resilience (Phase 26)

Implemented in [`router.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/ai/router.py).

## Resilience Controls
- **Timeouts**: Every provider call enforces `timeout` (default `AI_REQUEST_TIMEOUT`).
- **Bounded Retries & Backoff**: Transient errors (`AIProviderRateLimitError`, `AIProviderTimeoutError`, `AIProviderUnavailableError`) retry up to `AI_MAX_RETRIES` times with exponential backoff (`AI_RETRY_BACKOFF_SECONDS * 2^attempt`, capped at `5.0s`). `AIProviderAuthError` is never retried.
- **Circuit Breaker**: Tracks consecutive failures per provider. After `AI_CIRCUIT_BREAKER_THRESHOLD` failures, the circuit opens for `AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS` and fast-fails without hammering the failing provider.
- **Privacy & Selection Rules**: `LOCAL_ONLY_AI=true` strictly blocks external providers (`gemini`, `grok`) and routes only to `ollama`. Explicit provider selection never silently switches to another provider.
- **Health Visibility**: `AIProviderRouter.get_status()` exposes `circuit_state`, `consecutive_failures`, `total_successes`, `total_failures`, and `last_error_class` without exposing credentials.
