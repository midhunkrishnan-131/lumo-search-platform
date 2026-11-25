# LUMO Operations, Deployment, Backup & Recovery Guide (Phase 21)

## 1. Installation Guide (Windows 11)
- **System Requirements**: Windows 11, Python 3.11+ (tested on Python 3.14), 16 GB RAM recommended, optional PostgreSQL 16+, optional Qdrant server, optional Ollama.
- **One-Command Setup**:
  ```bat
  setup_lumo.bat
  ```
  This validates Python, creates `backend\.venv`, installs `backend\requirements.txt`, copies `backend\.env.example` to `backend\.env` if missing, applies non-destructive schema checks, and runs `check_lumo.bat`.

---

## 2. Startup, Shutdown & Lifecycle Guide
- **Start LUMO**: `start_lumo.bat` (launches FastAPI on `http://127.0.0.1:8000` and Frontend on `http://127.0.0.1:3000`; skips duplicate instances).
- **Stop LUMO**: `stop_lumo.bat` (stops only listeners on ports `8000` and `3000`).
- **Restart LUMO**: `restart_lumo.bat`.
- **Diagnostics Check**: `check_lumo.bat` (or `GET /api/v1/ops/diagnostics`).
- **Safe Update**: `update_lumo.bat` (creates a `pre_update` backup, verifies dependencies, and applies non-destructive schema checks).

---

## 3. Deployment Options
### Option A: Local Windows Deployment (Default)
Run `start_lumo.bat`. Backend binds to `127.0.0.1:8000`, frontend to `127.0.0.1:3000`, using SQLite (`lumo.db`) or local PostgreSQL and embedded `./qdrant_storage`.

### Option B: Private Server Deployment (Linux + HTTPS Reverse Proxy)
See [`DEPLOYMENT.md`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/DEPLOYMENT.md) for Nginx HTTPS reverse proxy configuration. Always set:
- `ENVIRONMENT=production`
- `API_AUTH_TOKEN=<strong-random-token>`
- `CORS_ORIGINS=https://your-domain.example`
- Keep PostgreSQL (`5432`), Qdrant (`6333`), and Ollama (`11434`) bound to `127.0.0.1` only.

### Option C: Optional Containerized Deployment
An optional [`docker-compose.yml`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/docker-compose.yml) + [`backend/Dockerfile`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/Dockerfile) is provided for Linux/server hosts (`docker compose up -d`). Windows local users do not need Docker.

---

## 4. Backup & Retention Guide
Backups are stored in timestamped directories under `backups/YYYY-MM-DD_HHMMSS_ffffff/` with `database/`, `documents/`, `vector_store/`, and SHA-256 `manifest.json`.
- **CLI**:
  ```bat
  cd backend
  .venv\Scripts\python.exe -m app.ops.cli backup --label manual
  .venv\Scripts\python.exe -m app.ops.cli list-backups
  .venv\Scripts\python.exe -m app.ops.cli verify <backup_id>
  ```
- **API**: `POST /api/v1/ops/backups`, `GET /api/v1/ops/backups`, `POST /api/v1/ops/backups/{id}/verify`, `POST /api/v1/ops/backups/prune?keep=5`.

---

## 5. Recovery Guide
Restoration verifies every SHA-256 checksum in `manifest.json`, creates an automatic `pre_restore_<id>` safety backup first, and **requires explicit confirmation**:
```bat
cd backend
.venv\Scripts\python.exe -m app.ops.cli restore <backup_id> --confirm
```
Or via API: `POST /api/v1/ops/backups/{backup_id}/restore` with `{"confirm": true}`.

---

## 6. Configuration & Security Guide
- Secrets (`GEMINI_API_KEY`, `GROK_API_KEY`, `API_AUTH_TOKEN`, `DATABASE_URL`) live only in `backend/.env` (gitignored).
- Rotating logs (`backend/logs/lumo.log`, 5 MB × 5 files) automatically redact URL passwords, API keys, and Bearer tokens via `RedactingFormatter`.
- Enable `LOCAL_ONLY_AI=true` to block all external AI provider calls.

---

## 7. Troubleshooting
- **Port already in use**: Run `stop_lumo.bat` then `start_lumo.bat`.
- **Database connection failed**: Verify `DATABASE_URL` in `backend/.env` or leave SQLite fallback active for local single-user mode.
- **Ollama shows OPTIONAL / Offline**: Ollama is optional (`OLLAMA_ENABLED=false` by default). Start Ollama (`ollama serve`) and set `OLLAMA_ENABLED=true` to enable local models.
- **High RAM usage**: Keep `MAX_PROFILE_ROWS=50000` for datasets and avoid running large Ollama models simultaneously with heavy embedding jobs on 16 GB RAM.
