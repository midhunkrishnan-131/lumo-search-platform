# LUMO Windows Desktop Application (Phase 13)

LUMO Desktop wraps the existing FastAPI backend and Vanilla HTML/CSS/JS frontend inside a lightweight native Windows 11 desktop window powered by **Microsoft Edge WebView2** (`pywebview`).

---

## 1. Architecture & Framework Choice

- **Desktop Shell**: `pywebview` (`gui="edgechromium"`), utilizing the native Windows Edge WebView2 runtime.
  - **Why not Tauri**: Tauri requires installing the Rust toolchain (`rustc`, `cargo`) and MSVC C++ Build Tools.
  - **Why not Electron**: Electron bundles an additional ~150MB Chromium binary and Node.js runtime.
  - **Why `pywebview`**: Uses Windows's built-in WebView2 runtime, requires zero compiler toolchains, preserves 100% of `lumo-frontend/`, and integrates natively with Python lifecycle management.
- **Backend**: Managed local FastAPI (`uvicorn`) instance on `127.0.0.1:8000` (with dynamic free-port fallback).
- **Frontend**: Local `ThreadingHTTPServer` bound strictly to `127.0.0.1:3000` serving `lumo-frontend/`.

---

## 2. Application Lifecycle

1. **Splash Window**: Opens immediately with a monochrome loading screen.
2. **Duplicate Instance & Port Safety**:
   - Probes `127.0.0.1:8000/api/v1/health`. If a healthy LUMO instance is already running, the desktop shell attaches to it without spawning a duplicate.
   - If port `8000` or `3000` is occupied by an unrelated process, LUMO automatically allocates an ephemeral free local port and never terminates unrelated processes.
3. **Managed Startup & Watchdog**:
   - Launches FastAPI with `CREATE_NO_WINDOW` (no background console popup) and polls `/api/v1/health`.
   - A watchdog checks backend health every 10 seconds and restarts the managed backend if it exits unexpectedly.
4. **Graceful Exit**:
   - Closing the desktop window triggers `DesktopServiceManager.shutdown()`, terminating only processes started by this desktop instance.

---

## 3. Desktop Security

- **Origin Isolation**: All local servers bind strictly to `127.0.0.1` (loopback only, never `0.0.0.0`).
- **No Arbitrary Bridge (`js_api=None`)**: The WebView2 context has no Python-to-JS RPC bridge that could execute OS commands or read/write arbitrary local files.
- **Secret Protection**: API keys (`GEMINI_API_KEY`, `GROK_API_KEY`, `GUARDIAN_VIRUSTOTAL_API_KEY`) remain strictly in backend `.env` / process memory and are never exposed to the frontend or diagnostics JSON.
- **XSS Prevention**: Splash and startup error screens HTML-escape all dynamic strings.

---

## 4. Local Data Architecture

By default, LUMO Desktop stores user data in `%LOCALAPPDATA%\LUMO` (configurable via `LUMO_DATA_DIR`):

- `lumo.db` — SQLite local database (documents, search history, research sessions, guardian records, knowledge graph entities/relationships) unless PostgreSQL is configured in `backend/.env`.
- `qdrant_storage/` — Local Qdrant vector embeddings.
- `logs/` — `desktop.log` and `backend_desktop.log`.
- `temp/` — Safe temporary file spooling (automatically cleaned after Guardian scans).
- `webview/` — Edge WebView2 persistent `localStorage` (theme, preferences, endpoint).

Upgrading the application never deletes `%LOCALAPPDATA%\LUMO`.

---

## 5. Running & Packaging on Windows

### Quick Launch (Development / Source Mode)
From the repository root in PowerShell:
```powershell
.\launch_desktop.ps1
```

### Packaging as a Standalone Windows Bundle
```powershell
.\desktop\build_desktop.ps1
```
This uses `desktop/lumo_desktop.spec` with PyInstaller to generate `dist\LUMO\LUMO.exe`.

---

## 6. Troubleshooting

- **Backend fails to start**: Check `%LOCALAPPDATA%\LUMO\logs\backend_desktop.log`.
- **Port 8000 or 3000 busy**: LUMO automatically switches to a free local port and updates the desktop frontend `apiBaseUrl` automatically.
- **WebView2 missing**: Windows 11 includes Edge WebView2 by default; on older systems, install the Microsoft Edge WebView2 Evergreen Runtime.
