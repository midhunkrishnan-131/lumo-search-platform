# LUMO Standardized Error Handling (Phase 26)

## Error Categories (`app/core/observability.py`)
- `validation_error` (HTTP 400 / 422)
- `authentication_error` (HTTP 401)
- `authorization_error` (HTTP 403)
- `provider_error` (HTTP 502 / 503, `AIProviderError`)
- `database_error` (SQLAlchemy / SQLite errors)
- `network_error` (`httpx` / connection errors)
- `timeout_error` (HTTP 408 / 504, timeout exceptions)
- `resource_error` (HTTP 404 / 409 / 413 / 429, `OSError`)
- `internal_error` (HTTP 500 fallback)

## API Error Response Format
All handled HTTP, validation, and unhandled exceptions return JSON containing:
```json
{
  "detail": "Safe human-readable error message",
  "error_category": "validation_error",
  "request_id": "..."
}
```
Stack traces are logged server-side with secret redaction and are never returned to clients.
