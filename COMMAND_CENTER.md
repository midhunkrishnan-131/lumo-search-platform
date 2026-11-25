# LUMO Phase 19 — Intelligence Command Center

The **Intelligence Command Center** (`command-center.html`) serves as LUMO's unified operational dashboard, aggregating real-time metrics, activity, research, automations, AI provider status, data intelligence, knowledge graph, Download Guardian, notifications, and cached system health without duplicating module storage or business logic.

---

## 1. Architecture

- **Thin Backend Aggregation (`backend/app/api/routes/dashboard.py`)**: Queries existing SQLAlchemy models (`Document`, `WorkspaceItem`, `ResearchSession`, `Entity`, `Automation`, `AutomationExecution`, `AutomationNotification`, `UniversalImportJob`, `UniversalDataset`, `UniversalAnalysisReport`, `GuardianAnalysis`, `SearchHistory`, `PersonalizationSettings`, `TopicProfile`) with graceful partial-failure handling.
- **Cached System Health**: `GET /api/v1/dashboard/system-health` wraps `health.diagnostics()` with a 10-second TTL in-memory cache so repeated dashboard loads remain fast and non-intrusive.
- **Vanilla Frontend (`lumo-frontend/command-center.html` & `js/command-center.js`)**: Uses `Promise.allSettled()` so individual module errors never block other panels, and renders all content safely via `escapeHtml()`.

---

## 2. Dashboard APIs (`/api/v1/dashboard/*`)

- `GET /overview` — Real database counts across all modules + `degraded_sections`.
- `GET /activity?limit=25&offset=0&category=all` — Chronological unified feed across searches, research, imports, reports, automations, and Guardian.
- `GET /research` — Research session counts and recent sessions.
- `GET /automations` — Active/paused counts, automations, and recent executions.
- `GET /ai-status` — Safe AI Provider Router status (no API keys) + recent analysis reports.
- `GET /knowledge` — Workspace items, collections, notes, top topics, Knowledge Graph counts, and personalization opt-in state.
- `GET /guardian` — Recent Guardian analyses with non-definitive risk disclaimer.
- `GET /system-health?force=false` — Cached diagnostics (database, Qdrant, Ollama, AI providers, index counts).
- `GET /notifications?limit=20&unread_only=false` — Unread count and recent `AutomationNotification` items.

---

## 3. Dashboard Customization

Click **Customize Layout** in [`command-center.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/command-center.html) to:
- Show or hide individual panels
- Reorder panels (`Up` / `Down`)
- Reset to the default layout

Preferences are persisted locally in `localStorage` (`lumo_cc_layout_v1`).

---

## 4. Testing & Performance

Run Phase 19 tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_command_center.py -v
```

### Troubleshooting
- **Panel shows "Unavailable"**: Ensure the FastAPI backend is running on `http://127.0.0.1:8000` (configured in `Settings`) and check `GET /api/v1/dashboard/system-health`.
