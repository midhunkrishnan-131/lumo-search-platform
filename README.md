# LUMO — Private, Intelligent Search Engine

LUMO is a privacy-first, high-performance search engine built with a modern Vanilla JavaScript/CSS frontend and a Python/FastAPI backend foundation.

---

## Workspace Structure

```text
lumo/
├── backend/                FastAPI backend service, Web Crawler, Extractor, Classic, Semantic, Hybrid, AI Search, Research Agent, Download Guardian & Knowledge Graph
│   ├── app/
│   │   ├── main.py         Application instance, CORS, middleware, routers
│   │   ├── config.py       Pydantic Settings (.env configuration)
│   │   ├── api/routes/     API endpoints (health, crawler, documents, search, history, semantic, ai_search, research, guardian, graph, workspace)
│   │   ├── crawler/        Modular web crawler (validator, robots, fetcher, extractor, engine)
│   │   ├── processor/      Content cleaner, metadata extractor, and deduplication
│   │   ├── search/         Classic keyword search, snippets, and Hybrid RRF Orchestrator
│   │   ├── semantic/       Chunker, embedding service, Qdrant store, and Semantic engine
│   │   ├── ai/             AI Provider Router (Gemini, Grok, Ollama), Context Builder, and Citations
│   │   ├── research/       Autonomous Research Agent (Planner, Executor, Collector, Analyzer, Gaps, Reporter, Controller)
│   │   ├── guardian/       Download Guardian (Validator, URL Analyzer, Network Inspector, File Analyzer, Reputation, Risk)
│   │   ├── graph/          Knowledge Graph (Extractor, Normalizer, Relationships, NetworkX Engine, Service)
│   │   ├── workspace/      Personal Workspace (Importer, Search, Grounded AI, Collections, Notes, Annotations)
│   │   ├── history/        Persistent search and browsing history
│   │   ├── core/           Logging with URL credential masking
│   │   ├── database/       SQLAlchemy 2.0 + Psycopg 3 engine, sessions, table creation
│   │   ├── models/         SQLAlchemy models (Document, CrawlSession, CrawlUrl, SearchHistory, BrowsingHistory, ResearchSession, GuardianAnalysis, Entity, Relationship)
│   │   └── schemas/        Pydantic request & response models
│   ├── tests/              Pytest test suite (185 passing tests across all phases)
│   ├── check_db.py         Quick diagnostic tool for PostgreSQL connectivity
│   ├── requirements.txt    Python dependencies
│   ├── .env.example        Environment template
│   └── README.md           Comprehensive backend setup and architecture guide
│
└── lumo-frontend/          Finished responsive frontend
    ├── index.html          Homepage & search interface
    ├── results.html        Search results (Classic, Semantic, Hybrid, AI Search)
    ├── research.html       Deep Research workspace
    ├── guardian.html       Download Guardian & URL inspection
    ├── graph.html          Knowledge Graph visualization
    ├── workspace.html      Personal Intelligence & Knowledge Workspace
    ├── settings.html       Settings, theme toggle, and FastAPI gateway configuration
    ├── js/                 Modular Vanilla JavaScript
    │   ├── api.js          Centralized API integration layer
    │   └── ...
    ├── css/                Design system and themes
    └── tests/              Node.js test suite for frontend core and health integration
```

---

## Quick Start (Windows 11)

### One-Command Launch (Recommended)
From the repository root in PowerShell:
```powershell
.\start_lumo.ps1
```
This validates your virtual environment, ensures `.env` is configured (with automatic SQLite fallback if PostgreSQL is offline), and launches both the FastAPI backend (`127.0.0.1:8000`) and Frontend (`127.0.0.1:3000`).

### 1. Run the Backend (FastAPI) Manually

From PowerShell:

```powershell
cd backend
py -3.14 -m venv .venv               # Or py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env               # Edit DATABASE_URL in .env if using PostgreSQL
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

The API will be available at:
- Liveness health check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
- Platform Diagnostics: [http://127.0.0.1:8000/api/v1/health/diagnostics](http://127.0.0.1:8000/api/v1/health/diagnostics)
- Interactive API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Readiness check: [http://127.0.0.1:8000/api/v1/ready](http://127.0.0.1:8000/api/v1/ready)

### 2. Run the Frontend

In a separate PowerShell window:

```powershell
cd lumo-frontend
py -3.14 -m http.server 3000 --bind 127.0.0.1
```

Or using Vite (if Node.js is installed):

```powershell
npm install
npm run dev
```

Visit the application at:
- **Homepage:** [http://127.0.0.1:3000/](http://127.0.0.1:3000/)
- **Settings & API Connection Test:** [http://127.0.0.1:3000/settings.html](http://127.0.0.1:3000/settings.html)

In Settings, enter `http://127.0.0.1:8000` as the **FastAPI Base URL**, click **Save endpoint**, then click **Test connection**.

---

## Testing

### Backend Tests (Python / Pytest)
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

### PostgreSQL Diagnostic Check
```powershell
cd backend
.\.venv\Scripts\python.exe check_db.py
```

### Frontend Tests (Node.js)
```powershell
cd lumo-frontend
node --test tests/*.test.js
```
*(All 8 frontend tests run natively without external test runner dependencies.)*
