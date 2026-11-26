# LUMO Health Monitoring (Phase 26)

## Endpoints
- `GET /health` and `GET /health/live` (and `/api/v1/health`, `/api/v1/health/live`): Liveness probe returning `status: "healthy"`, `application`, `version`.
- `GET /ready` and `GET /health/ready` (and `/api/v1/ready`, `/api/v1/health/ready`): Readiness probe checking database connectivity (`db_latency_ms`, `uptime_seconds`); returns `503` when DB is unavailable.
- `GET /api/v1/health/diagnostics`: Platform diagnostics covering DB latency, schema version, search index, knowledge graph, AI provider circuit breakers, background jobs (`active_total`, `failed_total`), storage, and API observability metrics.
- `GET /api/v1/system/info`: Non-sensitive system version, API version, phase (`26`), migration version, enabled modules, health, and uptime (protected when `API_AUTH_TOKEN` or `X-API-Key` is configured).

## Status Semantics
- `healthy` / `ready`: Core database connected; optional providers (Gemini, Grok, Ollama) do not mark core system unhealthy if unconfigured.
- `degraded` / `not_ready`: Database unavailable.
