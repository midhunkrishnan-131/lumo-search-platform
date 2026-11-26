# LUMO Knowledge Hub API Reference (Phase 28)

Implemented in [`knowledge_hub.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/api/routes/knowledge_hub.py) (owner-isolated via `X-LUMO-Owner`, permissions `workspace:read` / `workspace:write`):
- `GET /api/v1/knowledge/dashboard`
- `GET/POST /api/v1/knowledge/collections`, `PUT/DELETE /api/v1/knowledge/collections/{id}`
- `POST /api/v1/knowledge/items/save`, `GET /api/v1/knowledge/items`, `GET/DELETE /api/v1/knowledge/items/{id}`, `PATCH /api/v1/knowledge/items/{id}/move`
- `POST /api/v1/knowledge/search`
- `GET/POST /api/v1/knowledge/notes`, `PUT/DELETE /api/v1/knowledge/notes/{id}`
- `GET /api/v1/knowledge/tags`, `PUT /api/v1/knowledge/tags/{tag_name}`
- `GET/POST /api/v1/knowledge/relationships`, `GET /api/v1/knowledge/items/{id}/recommendations`
- `GET /api/v1/knowledge/timeline`
- `POST /api/v1/knowledge/context`
- `POST /api/v1/knowledge/import`, `GET /api/v1/knowledge/export?format=json|markdown`
