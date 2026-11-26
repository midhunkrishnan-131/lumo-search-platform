# LUMO Index Management (Phase 29)

- **UI**: [`index-management.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/index-management.html)
- **APIs** ([`retrieval.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/api/routes/retrieval.py)):
  - `POST /api/v1/retrieval/index`
  - `GET /api/v1/retrieval/index/stats`
  - `GET /api/v1/retrieval/index/items`
  - `POST /api/v1/retrieval/index/{record_id}/reindex`
  - `DELETE /api/v1/retrieval/index/{record_id}?confirm=true` (requires explicit `confirm=true`)
