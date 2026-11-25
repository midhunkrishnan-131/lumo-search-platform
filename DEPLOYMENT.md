# LUMO Web Deployment Readiness Guide

This document describes how to prepare and run LUMO as a production web application behind a reverse proxy (Nginx / Caddy / Traefik) with PostgreSQL and Qdrant. **Do not expose development services directly to the public internet without TLS and access controls.**

---

## 1. Environment Configuration (`backend/.env`)

For production deployment:

```ini
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://lumo_user:<strong-password>@127.0.0.1:5432/lumo
LOG_LEVEL=INFO
CORS_ORIGINS=https://search.yourdomain.com
```

### Security Checklist
- Set `ENVIRONMENT=production` (automatically disables `/docs`, `/redoc`, and `/openapi.json`).
- Never use `*` in `CORS_ORIGINS`; specify exact `https://` origins.
- Keep `GEMINI_API_KEY`, `GROK_API_KEY`, and `GUARDIAN_VIRUSTOTAL_API_KEY` strictly in server environment variables.
- Note: LUMO currently has no built-in multi-user authentication/JWT layer. If deploying beyond `127.0.0.1`, place authentication (e.g. OAuth2 Proxy, Basic Auth, or VPN/Tailscale) at the reverse proxy layer.

---

## 2. Backend Process (Uvicorn / Gunicorn)

Run FastAPI bound to `127.0.0.1:8000` behind your reverse proxy:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
```

*Note*: If using multiple workers (`--workers > 1`), use PostgreSQL (not SQLite) and a dedicated Qdrant server (`QDRANT_URL=http://127.0.0.1:6333`) instead of local embedded `./qdrant_storage` (which locks to one process).

---

## 3. Static Frontend & Reverse Proxy (Nginx Example)

Serve `lumo-frontend/` as static files over HTTPS and proxy `/api/` to FastAPI:

```nginx
server {
    listen 443 ssl http2;
    server_name search.yourdomain.com;

    root /var/www/lumo/lumo-frontend;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 30M;
    }
}
```

---

## 4. Health & Diagnostics Monitoring

- **Liveness**: `GET /api/v1/health` (returns `200 OK` when API is responsive)
- **Readiness**: `GET /api/v1/ready` (returns `503` if database is unavailable)
- **Diagnostics**: `GET /api/v1/health/diagnostics` (reports DB, Search Index, Knowledge Graph, Workspace, Crawler, Vector Store, and AI provider readiness without leaking secrets)
