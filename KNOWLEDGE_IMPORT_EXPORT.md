# LUMO Knowledge Import & Export (Phase 28)

- **Export**: `GET /api/v1/knowledge/export?format=json|markdown` exports only the authenticated owner's collections, items, and notes (no API keys or secrets).
- **Import**: `POST /api/v1/knowledge/import` validates schema, enforces `MAX_IMPORT_ITEMS = 200`, deduplicates items via SHA-256 `content_hash`, and never executes imported content.
