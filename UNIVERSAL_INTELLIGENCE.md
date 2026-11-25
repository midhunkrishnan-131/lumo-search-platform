# LUMO Phase 18 — Universal Data Intelligence Engine

The **Universal Data Intelligence Engine** extends LUMO to ingest, validate, classify, profile, index, analyze, visualize, and cross-reference multi-format documents, spreadsheets, structured datasets, web pages, and images locally.

---

## 1. Architecture & Pipeline

```
Input (File Upload / SSRF-Screened URL)
  ↓ File/Signature Validation & Size Caps (security.py)
  ↓ Format Detection (PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, JSONL, PNG/JPG/WebP)
  ↓ Content & Metadata Extraction (WorkspaceImporter / Spreadsheet Profiler / Image Metadata + Optional Local Tesseract OCR)
  ↓ Content Classification (Deterministic Keyword/Format + Optional AIProviderRouter)
  ↓ Storage & Indexing (WorkspaceItem + UniversalDataset + UniversalImportJob)
  ↓ Knowledge Graph Integration (EntityExtractor -> Entity upsert)
  ↓ Intelligence Availability (Workspace Search, Document Intelligence, AI Data Analyst, SVG Charts, Cross-Document Reports)
```

- **Restart Safety**: On startup, `UniversalIngestionPipeline.recover_interrupted_jobs()` marks any interrupted in-flight jobs as `failed` with retry readiness.
- **Deletion Synchronization**: `DELETE /api/v1/intelligence/imports/{import_id}` removes the `UniversalImportJob`, linked `UniversalDataset`, stored dataset blob under `backend/data/intelligence_datasets/`, and linked `WorkspaceItem`.

---

## 2. Supported Formats

| Category | Formats | Notes |
|---|---|---|
| Documents | `.pdf`, `.docx`, `.txt`, `.md`, `.markdown`, `.html`, `.htm` | Magic-byte & zip-bomb validated; reuses `WorkspaceImporter`. |
| Spreadsheets | `.csv`, `.xlsx` | Streaming row reader (`openpyxl read_only=True` for XLSX); multi-sheet support. |
| Structured Data | `.json`, `.jsonl` | Record flattening, schema profiling, and bounded streaming. |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` | Magic-byte validated, header dimension extraction, optional local `tesseract` CLI OCR if installed. |
| Web Content | `http://`, `https://` | SSRF-screened via `validate_guardian_url()`. |

---

## 3. Spreadsheet Intelligence, AI Data Analyst & Visualization

- **Streaming Profiling** (`spreadsheet.py`): Bounded at `MAX_PROFILE_ROWS = 50,000` rows to prevent OOM on 16GB RAM Windows systems. Computes column types (`integer`, `numeric`, `boolean`, `date`, `categorical`, `text`), missing values, duplicate row hashes, numeric statistics (`min`, `max`, `mean`, `median`, `std`, `sum`), category counts, date spans, and data quality observations.
- **AI Data Analyst**: `compute_deterministic_analysis()` performs all numerical calculations, missing-value breakdowns, category rankings, and Z-score outlier detection deterministically. Only verified metrics and schema metadata are passed to `AIProviderRouter` for explanation — the AI model never executes arbitrary code or invents statistics.
- **Data Visualization**: `generate_chart_data()` + `suggest_charts()` power responsive Vanilla JS SVG charts in [`intelligence.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/intelligence.html) for **Bar**, **Line**, **Pie**, **Histogram**, and **Scatter** plots with SVG export.

---

## 4. AI Provider Configuration & Security

- Providers (`gemini`, `grok`, `ollama`) are configured via environment variables in `backend/.env` (`GEMINI_API_KEY`, `GROK_API_KEY`, `AI_PRIMARY_PROVIDER`, `AI_FALLBACK_PROVIDER`, `LOCAL_ONLY_AI`).
- API keys are never exposed in frontend code or `GET /api/v1/intelligence/providers/status`.
- `redact_secrets()` scrubs API keys and `?key=` parameters from error messages and logs.
- Uploaded files are never executed and prompt content is sanitized via `ContextBuilder._sanitize_for_prompt()`.

---

## 5. API Endpoints (`/api/v1/intelligence/*`)

- `GET /providers/status` — Safe provider availability status.
- `POST /import` & `POST /import/url` — File upload or SSRF-screened URL ingestion.
- `GET /imports`, `GET /imports/{id}`, `POST /imports/{id}/retry`, `DELETE /imports/{id}`.
- `GET /documents`, `GET /documents/{id}`, `POST /documents/{id}/analyze`, `POST /documents/compare`.
- `GET /datasets`, `GET /datasets/{id}`, `GET /datasets/{id}/profile?sheet=...`, `POST /datasets/{id}/analyze`, `POST /datasets/{id}/visualize`.
- `POST /cross-analysis`, `GET /reports`, `GET /reports/{id}`.

---

## 6. Windows Setup & Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_intelligence.py -v
```

### Troubleshooting
- **Image OCR**: Image dimensions and metadata work out of the box; for full OCR text extraction on images, install Tesseract OCR for Windows and ensure `tesseract.exe` is on `PATH`.
- **Local-Only Privacy Mode**: Enable `LOCAL_ONLY_AI=true` in `backend/.env` to block external Gemini/Grok calls and route strictly to local Ollama or deterministic fallbacks.
