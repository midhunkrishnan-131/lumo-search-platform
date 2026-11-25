# LUMO Phase 23 — Intelligence API & Developer Platform Guide

## 1. API Architecture & Versioning
LUMO exposes versioned REST APIs under `/api/v1/*` with interactive OpenAPI documentation at `/docs` (automatically disabled when `ENVIRONMENT=production`) and request tracing via `X-Request-ID`.

| Namespace | Capability | Required Permission |
|---|---|---|
| `/api/v1/search` | Classic, Semantic, Hybrid Search | `search:read` |
| `/api/v1/ai` | AI Search & Grounded Generation | `ai:execute` |
| `/api/v1/research` | Autonomous Research Agent | `research:read` / `research:write` |
| `/api/v1/documents` | Document Storage & Extraction | `documents:read` / `documents:write` |
| `/api/v1/intelligence` | Universal Data Intelligence & Charts | `data_intelligence:read` / `data_intelligence:write` |
| `/api/v1/graph` | Knowledge Graph Queries | `graph:read` |
| `/api/v1/guardian` | Download Guardian URL/File Analysis | `guardian:execute` |
| `/api/v1/workspace` | Personal Workspace & Search | `workspace:read` / `workspace:write` |
| `/api/v1/integrations` | External Integration Layer | `integrations:read` / `integrations:sync` |
| `/api/v1/automations` | Intelligence Automation Engine | `automation:read` / `automation:execute` |
| `/api/v1/dashboard`, `/api/v1/ops` | System Health, Integrity, Diagnostics | `system:read` |

---

## 2. Authentication, Key Lifecycle & Permissions
- External clients authenticate with `X-API-Key: lumo_pk_...` or `Authorization: Bearer lumo_pk_...`.
- Keys are generated with `secrets.token_urlsafe(32)`, stored strictly as SHA-256 hashes (`key_hash`), and displayed **only once** upon creation or rotation.
- Keys support granular permission scopes, expiration (`expires_in_days`), immediate revocation, rotation, and deletion via [`developer.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/developer.html) or `/api/v1/developer/keys/*`.
- `lumo_pk_...` tokens are automatically redacted by `RedactingFormatter` and `redact_secrets()`.

---

## 3. Rate Limiting & Usage Monitoring
- Each API key enforces its own sliding-window `rate_limit_rpm` (returning `429` with `Retry-After: 60` when exceeded).
- `ApiUsageLog` records `key_prefix`, `endpoint`, `method`, `status_code`, `duration_ms`, and `rate_limited` without storing raw keys or request/document bodies.

---

## 4. Python SDK (`sdk/lumo_sdk.py`)
```python
from sdk.lumo_sdk import LumoClient

client = LumoClient("http://127.0.0.1:8000", api_key="lumo_pk_your_key")
res = client.search("FastAPI", mode="hybrid")
print(res["total"], res["results"])
```

---

## 5. Testing
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_developer_platform.py -v
```
