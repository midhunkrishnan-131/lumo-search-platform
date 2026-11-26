# LUMO Configuration Reference (Phase 26)

Settings are managed via `Settings` in [`config.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/config.py) with `.env` support and startup validation (`validate_startup_config()`).

## Core & Security Settings
- `ENVIRONMENT`: `development` | `production` | `test`
- `DATABASE_URL`: PostgreSQL (`postgresql+psycopg://...`) or `sqlite:///...` (empty falls back to `lumo.db`)
- `CORS_ORIGINS`: Explicit comma-separated `http://` or `https://` origins (wildcards rejected)
- `API_AUTH_TOKEN`: Optional bearer/`X-LUMO-Token` secret for LAN/production API protection
- `RATE_LIMIT_PER_MINUTE`: Default `240`

## Phase 26 Observability & Resilience Settings
- `LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` (default `INFO`)
- `LOG_FORMAT`: `auto` | `json` | `text` (default `auto`)
- `SLOW_REQUEST_THRESHOLD_MS`: Slow request warning threshold in ms (default `1000.0`)
- `AI_MAX_RETRIES`: Bounded retries for transient AI errors (default `1`)
- `AI_RETRY_BACKOFF_SECONDS`: Base exponential backoff in seconds (default `0.5`)
- `AI_CIRCUIT_BREAKER_THRESHOLD`: Consecutive failures before opening circuit (default `3`)
- `AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS`: Circuit open duration in seconds (default `60.0`)
- `JOB_STUCK_TIMEOUT_SECONDS`: Stuck job threshold in seconds (default `600`)
