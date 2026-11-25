# LUMO backend

FastAPI backend, Controlled Web Crawler, Content Extraction Pipeline, Classic Search Engine, Local Semantic Vector Search, Hybrid Search Engine with Reciprocal Rank Fusion, and Grounded AI Search with Provider Router for LUMO. This service provides environment-based configuration, structured logging, PostgreSQL connection pooling, a secure web crawler with SSRF protection, automated document deduplication, PostgreSQL Full Text Search, Sentence Transformers (`all-MiniLM-L6-v2`), local Qdrant vector retrieval, Hybrid Search (Classic + Semantic via RRF), multi-provider AI Search (Google Gemini, xAI Grok, Ollama) with prompt injection boundaries and verified citation resolution, and persistent Search & Browsing History with privacy controls.

The finished frontend in `lumo-frontend` is unchanged. The API runs beside it.

## Architecture

```
backend/
    app/
        main.py                 FastAPI app, lifecycle, CORS, error handling
        config.py               Pydantic Settings (.env and environment variables)
        api/routes/
            health.py           Liveness and readiness routes
            crawler.py          Crawler session, start, stop, and URL routes
            documents.py        Document retrieval, metadata, and processing routes
            search.py           Unified Search endpoint (Classic, Semantic dispatch)
            history.py          Search history, browsing tracking, privacy, and export
            semantic.py         Semantic Search & Vector Indexing management routes
            ai_search.py        Grounded AI Search, RAG generation, and provider status routes
            research.py         Autonomous Research Agent session, lifecycle, and report routes
            guardian.py         Download Guardian URL & File static analysis, history & deletion routes
            graph.py            Knowledge Graph overview, entity details, connections & stats routes
        graph/
            normalizer.py       Entity normalization, canonical alias mapping, and safe deduplication
            extractor.py        Entity extraction (vocabulary, structural regex, and optional grounded AI)
            relationships.py    Syntactic relationship extraction with sentence-level text evidence
            engine.py           NetworkX graph computation layer (BFS neighborhood, layout, centrality)
            service.py          PostgreSQL/SQLite graph persistence, sync, and indexing coordinator
        core/logging.py         Log setup and URL password redaction
        crawler/
            validator.py        URL validation, normalization, and SSRF shield
            robots.py           robots.txt parser and domain caching
            fetcher.py          Safe HTTP fetching with size and redirect guards
            extractor.py        HTML link extraction and normalization
            engine.py           Local crawl loop and state management
        processor/
            cleaner.py          HTML boilerplate removal (scripts, styles, nav, ads)
            extractor.py        Structured content & metadata extractor, text normalizer
            pipeline.py         Document processing and SHA-256 deduplication pipeline
        search/
            engine.py           PostgreSQL Full Text Search engine with weighted ranking
            snippet.py          HTML-safe context snippet extraction and query highlighting
            hybrid.py           Hybrid search orchestrator, RRF ranking, and graceful degradation
        history/
            service.py          Persistent search and browsing event recording & privacy
        ai/
            base.py             Common AI provider abstraction & custom exceptions
            gemini.py           Google Gemini API adapter (official HTTPS REST)
            grok.py             xAI Grok API adapter (OpenAI-compatible HTTPS)
            ollama.py           Optional local Ollama adapter (HTTP)
            router.py           AI Provider Router, provider selection & resilient fallback
            context.py          Context Builder, character budget & injection sanitization
            prompts.py          System prompts with strict untrusted data boundaries
            citations.py        Citation parser, validation & phantom citation removal
            orchestrator.py     End-to-end RAG orchestrator combining Hybrid retrieval & AI
        research/
            planner.py          Research Planner: topic decomposition into objectives & subquestions
            executor.py         Research Executor: Hybrid search with query deduplication
            evidence.py         Evidence Collector: passage deduplication & stable [S1] mapping
            analyzer.py         Evidence Analyzer: findings, contradictions & information gaps
            gaps.py             Gap Detector: synthesizes bounded follow-up queries
            citations.py        Research Citation Registry & markdown validator
            reporter.py         Structured 12-section research report generator
            controller.py       Research Controller: bounded multi-step autonomous loop
            manager.py          Research Session Manager: thread worker, state & CRUD
        guardian/
            validator.py        URL validator, normalization, and SSRF & private IP screening
            url_analyzer.py     Static URL structure, homograph, shortener, and pattern inspector
            network.py          Safe redirect tracing, per-hop SSRF validation & TLS inspector
            file_analyzer.py    Safe static file inspection, hashing, magic bytes, zip-slip, entropy
            reputation.py       Reputation provider abstraction & optional VirusTotal v3 adapter
            risk.py             Deterministic evidence-based risk assessment & recommendations
            explainer.py        Optional plain-English AI explainer of security findings
        semantic/
            chunker.py          Document text chunker with paragraph and overlap control
            embedding.py        Local embedding service (all-MiniLM-L6-v2, 384-d vectors)
            vector_store.py     Qdrant REST API client with local persistent fallback
            indexer.py          Semantic indexing and vector synchronization pipeline
            search.py           Semantic vector similarity search with document aggregation
        database/
            connection.py       SQLAlchemy engine, sessions, table creation
        models/
            crawler.py          CrawlSession and CrawlUrl SQLAlchemy models
            document.py         Document SQLAlchemy model with semantic indexing status
            history.py          SearchHistory and BrowsingHistory SQLAlchemy models
            research.py         ResearchSession SQLAlchemy model with state & audit trail
            guardian.py         GuardianAnalysis SQLAlchemy model for audit trail & findings
        schemas/
            crawler.py          Crawler Pydantic request and response schemas
            document.py         Document Pydantic schemas
            search.py           Search query and response schemas
            history.py          History and privacy schemas
            semantic.py         Semantic indexing and status schemas
            ai.py               AI Search request, citation, and response schemas
            research.py         Research session, plan, finding, and report schemas
            guardian.py         Guardian URL & File analysis request, finding, and history schemas
    tests/                      Comprehensive test suite (164 unit/integration tests)
    check_db.py                 PostgreSQL diagnostic CLI tool
    .env                        Local settings (not committed)
    .env.example                Safe template
    requirements.txt
```

System Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Liveness. Does not check PostgreSQL. |
| GET | `/health` | Same payload. Backward-compatible alias. |
| GET | `/api/v1/ready` | Readiness. `200` when PostgreSQL accepts a connection, otherwise `503`. |

Crawler Endpoints (Phase 3):

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/crawler/sessions` | Create a new crawl session with validated seed URLs. |
| POST | `/api/v1/crawler/sessions/{session_id}/start` | Launch local background crawling for the session. |
| POST | `/api/v1/crawler/sessions/{session_id}/stop` | Gracefully halt an active crawl session. |
| GET | `/api/v1/crawler/sessions/{session_id}` | Fetch session progress, status, and URL counts. |
| GET | `/api/v1/crawler/sessions` | List all crawl sessions (with pagination). |
| GET | `/api/v1/crawler/sessions/{session_id}/urls` | List discovered URLs, status, depth, and HTTP codes. |
| GET | `/api/v1/crawler/sessions/{session_id}/documents` | List extracted documents for a crawl session. |

Document Processing Endpoints (Phase 4):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/documents` | List processed documents with filtering (session, duplication, status) and pagination. |
| GET | `/api/v1/documents/{document_id}` | Fetch full document content, headings, and metadata. |
| GET | `/api/v1/documents/{document_id}/metadata` | Fetch document metadata without full text body. |
| POST | `/api/v1/documents/process` | Directly extract, normalize, deduplicate, and persist an HTML document. |

Classic Search Endpoints (Phase 5):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/search` | Full-text keyword search across titles, descriptions, and content with ranking, filtering, pagination, and snippet extraction. |

Semantic Search Endpoints (Phase 6):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/semantic/search` | Semantic vector similarity search with document-level aggregation and contextual snippets. |
| GET | `/api/v1/search?mode=semantic` | Unified search endpoint routing to Semantic Search (used by frontend `searchSemantic`). |
| POST | `/api/v1/semantic/index/{document_id}` | Chunk, embed, and index a document into the local Qdrant vector store. |
| POST | `/api/v1/semantic/reindex/{document_id}` | Re-chunk and regenerate vector embeddings for an existing document. |
| GET | `/api/v1/semantic/index/status` | Vector index diagnostics (document counts, vector count, model name, Qdrant health). |
| GET | `/api/v1/semantic/index/{document_id}` | Document semantic indexing status and chunk count. |
| POST | `/api/v1/semantic/index/pending` | Batch index pending non-duplicate documents into vector storage. |

Hybrid Search Endpoints (Phase 7):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/search/hybrid` | Dedicated Hybrid Search endpoint fusing Classic and Semantic retrieval using Reciprocal Rank Fusion (RRF). |
| GET | `/api/v1/search?mode=hybrid` | Unified search endpoint routing to Hybrid Search with full query deduplication and rank fusion. |

AI Search & RAG Endpoints (Phase 8):

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/search/ai` | Grounded AI question answering and research reports using Hybrid retrieval, prompt injection defense, and verified `[S1]` citations. |
| GET | `/api/v1/search/ai/status` | Diagnostic endpoint returning configured status of AI providers without exposing API keys. |
| GET | `/api/v1/search?mode=ai` | Unified search endpoint routing to AI Search with full grounded response metadata. |

Autonomous Research Agent Endpoints (Phase 9):

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/research` | Initialize a bounded, multi-step autonomous research session (auto-starts in background by default). |
| POST | `/api/v1/research/{session_id}/start` | Manually start execution of an existing pending research session. |
| GET | `/api/v1/research/{session_id}` | Detailed research session status, plan, live queries executed, sources, findings, and report. |
| GET | `/api/v1/research/{session_id}/report` | Completed structured research report with validated source citations. |
| GET | `/api/v1/research/{session_id}/sources` | Complete list of collected evidence sources and provenances. |
| POST | `/api/v1/research/{session_id}/cancel` | Gracefully terminate an active research session. |
| GET | `/api/v1/research` | Paginated listing of past and active research sessions. |
| DELETE | `/api/v1/research/{session_id}` | Delete a research session and its associated report and artifacts. |

Download Guardian Security Endpoints (Phase 10):

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/guardian/url` | Defensively inspect a URL (SSRF screening, structure, redirect hops, TLS cert, risk score). |
| POST | `/api/v1/guardian/file` | Defensively analyze an uploaded file or client SHA-256 hash (magic bytes, zip-slip, entropy, risk score). |
| GET | `/api/v1/guardian/analysis/{analysis_id}` | Retrieve full historical analysis report with all findings and metadata. |
| GET | `/api/v1/guardian/history` | List previous security analysis reports (paginated). |
| DELETE | `/api/v1/guardian/analysis/{analysis_id}` | Delete a specific analysis report from database history. |
| DELETE | `/api/v1/guardian/history` | Clear all security analysis history. |

Search & Browsing History Endpoints (Phase 5):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/history/search` | List persistent search history queries with timestamps and result counts. |
| DELETE | `/api/v1/history/search/{item_id}` | Delete a single search history entry. |
| DELETE | `/api/v1/history/search` | Clear all search history records. |
| POST | `/api/v1/history/browse` | Record a webpage or search result visit (dwell time, URL, document link). |
| GET | `/api/v1/history/browse` | List visited pages history. |
| DELETE | `/api/v1/history/browse/{item_id}` | Delete a single browsing history entry. |
| DELETE | `/api/v1/history/browse` | Clear all browsing history records. |
| GET | `/api/v1/history/export` | Export complete search and browsing history as a JSON bundle. |

Health response:

```json
{
  "status": "healthy",
  "application": "LUMO",
  "version": "0.1.0"
}
```

Readiness response:

```json
{
  "status": "ready",
  "application": "LUMO",
  "checks": {
    "database": "connected"
  }
}
```

When PostgreSQL is down or not configured, `status` is `not_ready`, `database` is `unavailable`, and the HTTP status is `503`. The body does not include the host, username, password, or driver error.

The server binds to `127.0.0.1` so it is only reachable from this computer. CORS allows the local frontend origins `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5500`, and `http://127.0.0.1:5500` (Vite and Cursor Live Preview). Wildcard CORS is rejected.

## Windows setup

Use Python 3.12 or newer. These commands assume PowerShell and the `backend` directory.

### 1. Create a virtual environment

```powershell
cd backend
py -3.14 -m venv .venv
```

If `py -3.14` is not available, use `py -3` instead.

You can run the virtual environment without activating it. That avoids PowerShell execution-policy prompts:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

To activate it instead:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Install PostgreSQL

PostgreSQL is not started by this repository. Install the free Windows build once:

1. Download the installer from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/).
2. Install PostgreSQL 16 or 17.
3. Remember the password you set for the `postgres` role.
4. Keep the default port `5432`.
5. Confirm the Windows service is running. In PowerShell:

```powershell
Get-Service -Name "postgresql*"
```

Open **SQL Shell (psql)** from the Start menu, accept the defaults, and sign in as `postgres`. Then create a dedicated database role. Do not use a superuser for the app.

```sql
CREATE USER lumo_user WITH PASSWORD 'choose-a-local-password';
CREATE DATABASE lumo OWNER lumo_user;
```

`choose-a-local-password` is only an example. Pick your own password. If the password contains `@`, `:`, `/`, or `#`, URL-encode it inside `DATABASE_URL`.

### 3. Configure the environment

```powershell
copy .env.example .env
```

A starter `.env` is already present for local development. Edit `DATABASE_URL` so it matches the role and password you created:

```text
DATABASE_URL=postgresql+psycopg://lumo_user:choose-a-local-password@127.0.0.1:5432/lumo
```

The URL must use the `postgresql+psycopg://` scheme. That selects SQLAlchemy with the Psycopg driver. Leave the other values as they are unless you need a different frontend origin.

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | Application name returned by health checks. |
| `APP_VERSION` | Version returned by health checks. |
| `ENVIRONMENT` | `development`, `test`, or `production`. |
| `DATABASE_URL` | PostgreSQL URL. Empty disables the database without stopping the API. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `CORS_ORIGINS` | Comma-separated browser origins. `*` is rejected. |

`.env` is listed in `.gitignore`. Do not commit it.

### 4. Run FastAPI

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

`--no-access-log` avoids a second access log. The application logs startup, shutdown, requests, and database status itself. Interactive API docs are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) when `ENVIRONMENT` is not `production`.

### 5. Test the health endpoint

In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready
```

`/api/v1/health` should show `healthy` even when PostgreSQL is not running.

`/api/v1/ready` is the PostgreSQL check:

- `status: ready` and HTTP 200 means the database accepted `SELECT 1`.
- `status: not_ready` and HTTP 503 means the database is not configured or refused the connection. The server log names the failure type and the host, but not the password.

`curl.exe http://127.0.0.1:8000/api/v1/health` works as well. In PowerShell, the `curl` alias is `Invoke-WebRequest`, so use `curl.exe` if you want curl.

### 6. Test PostgreSQL connectivity (CLI tool)

You can also test the database connection directly without starting the web server:

```powershell
.\.venv\Scripts\python.exe check_db.py
```

This script reads `DATABASE_URL` from `.env`, attempts a `SELECT 1` ping, prints clean diagnostic feedback, and masks any database passwords.

### 7. Run tests

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The database tests check credential redaction, failed connections, and session cleanup. They do not need a running PostgreSQL server. A live server is still required before `/api/v1/ready` can report `connected`.

## Frontend communication

The homepage is not modified. Frontend and API run separately.

1. Start the API on `http://127.0.0.1:8000`.
2. Serve the finished frontend from `lumo-frontend` so `/js`, `/css`, and `/assets` resolve correctly. Do not open `index.html` as a file, and do not start Live Preview from the repository root.

```powershell
cd ..\lumo-frontend
py -3.14 -m http.server 3000 --bind 127.0.0.1
```

Vite also works if you prefer it:

```powershell
npm install
npm run dev
```

3. Open [http://127.0.0.1:3000/](http://127.0.0.1:3000/) for the homepage, or [http://127.0.0.1:3000/settings.html](http://127.0.0.1:3000/settings.html) to test the API.
4. Set **FastAPI Base URL** to `http://127.0.0.1:8000` and save it.
5. Click **Test connection**.

The settings page calls `GET /health`. A normal response means the browser reached FastAPI and CORS allowed `http://localhost:3000`. Leave the base URL blank to keep sample demonstration mode.

Search, research, guardian, and graph routes are not part of this phase. Those pages keep using sample data until a base URL is saved, and they will receive `404` from the API if a base URL is saved before those routes exist.

## Logging

Logs use this form:

```text
2026-11-25 10:00:00 | INFO | lumo.app | Application startup: LUMO version 0.1.0 (development)
```

The API logs startup, shutdown, method, path, status code, and duration. It does not log query strings, request bodies, or the `Authorization` header. Database logs include host, port, and database name only. A formatter also masks passwords that appear in `scheme://user:password@host` text.

## Troubleshooting

**`python` is not found, or it opens the Microsoft Store.** Use `py -3.14 -m venv .venv`.

**PowerShell blocks `Activate.ps1`.** Skip activation and call `.\.venv\Scripts\python.exe` directly, or run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for the current window only.

**`DLL load failed` for a SQLAlchemy file, or Windows says an Application Control policy blocked it.** Install the pinned requirements. This project uses SQLAlchemy 2.0.58 because the SQLAlchemy 2.1 Windows build loads compiled extensions that some Windows 11 policies reject. The 2.0 release uses a pure-Python fallback.

**`ModuleNotFoundError: app`.** Run Uvicorn and pytest from the `backend` directory, not the repository root.

**Health works, readiness is `not_ready`.** PostgreSQL is not running, or `DATABASE_URL` is wrong. Check the Windows service, the database name, the role, and the password. The API stays up so `/api/v1/health` can still be tested.

**`connection refused` in the log type `OperationalError`.** Nothing is listening on `127.0.0.1:5432`. Start the PostgreSQL service. Use `127.0.0.1` in `DATABASE_URL` so Windows does not also wait on the IPv6 address for `localhost`. Readiness can take a few seconds while that connection attempt times out.

**`password authentication failed`.** Update the password in `.env`, then restart Uvicorn. Do not put that password in source files.

**Settings test says the health check failed.** Save `http://127.0.0.1:8000` with no trailing path. The page adds `/health` itself. Confirm the API is running and that you opened the frontend from `http://localhost:3000` or `http://127.0.0.1:3000`.

**Browser CORS error from another port.** Add that exact origin to `CORS_ORIGINS` and restart Uvicorn. Do not use `*`.

**Port 8000 is already in use.** Start Uvicorn with `--port 8001` and use that port in the settings page and in `CORS` testing. Keep the host as `127.0.0.1`.

**OneDrive file locks under `.venv`.** This project lives in OneDrive. Exclude `backend\.venv` from sync if installs fail with access-denied errors.

**Interactive docs are missing.** `/docs` is disabled when `ENVIRONMENT=production`. Use `development` on this computer.
