# LUMO Personal Intelligence & Knowledge Workspace

The Personal Workspace (`lumo-frontend/workspace.html`, `/api/v1/workspace/*`) is a private, local-first knowledge base integrated into LUMO.

---

## 1. Architecture & Data Storage

- **Relational Tables (`backend/app/models/workspace.py`)**:
  - `workspace_collections`: User collections (supports optional `parent_id`).
  - `workspace_tags`: Normalized tags (`name`, `display_name`).
  - `workspace_items`: Saved web pages, search results, research reports, Knowledge Graph entities, and imported files (`content_hash` for SHA-256 deduplication, `last_viewed_at` tracking).
  - `workspace_item_tags`, `workspace_note_tags`: Many-to-many tag associations.
  - `workspace_notes`: Markdown notes with optional links to `collection_id`, `linked_item_id`, `linked_entity_id`, and `linked_research_id`.
  - `workspace_annotations`: Highlights/quotes (`selected_text`), user comments, and character offsets (`start_offset`, `end_offset`) anchored to `WorkspaceItem`.
- **Privacy Isolation**:
  - All personal data is stored strictly in `workspace_*` tables and never mixed into the general `documents` web-index table.
  - Designed for **single-user local deployment**. If deploying publicly, place authentication at the reverse proxy layer (see `DEPLOYMENT.md`).

---

## 2. Document & URL Import

- **Supported Local File Types**: `.pdf` (`pypdf`), `.txt`, `.md`/`.markdown`, `.html`/`.htm` (`app.processor.extractor`), and `.docx` (bounded ZIP/XML extraction with zip-bomb and DOCTYPE guards).
- **Limits & Safety**: Max 25 MB upload, max 200 PDF pages, path-traversal filename stripping, no file execution, and no automatic third-party uploads.
- **URL Import**: Validates URLs through `validate_guardian_url()` (SSRF shield blocking loopback/private/cloud-metadata IPs) before fetching.

---

## 3. Personal Search & Grounded AI Q&A

- **Personal Search (`POST /api/v1/workspace/search`)**: Searches saved items, notes, and annotations in **Keyword**, **Semantic**, or **Hybrid (RRF)** modes, filtered by collection, source type, or tag.
- **Personal AI Assistant (`POST /api/v1/workspace/ask`)**:
  - Retrieves top workspace sources, sanitizes text via `ContextBuilder._sanitize_for_prompt()`, and queries `AIProviderRouter` (Gemini, Grok, or Ollama).
  - Enforces `[W1]`/`[W2]` workspace citations and strips hallucinated citation keys.
  - Remains completely optional; returns `provider_unavailable` with retrieved sources if no AI provider is configured.

---

## 4. Knowledge Graph & Cross-Module Saving

- **Save to Workspace**: Available directly from Search Results (`results.js`), Research Agent Reports (`research.js`), and Knowledge Graph Entity Inspector (`graph.js`).
- **Graph Connections (`GET /api/v1/workspace/items/{id}/connections`)**: Extracts entities mentioned in a workspace item and links them to persisted Knowledge Graph entities and related workspace items without exposing personal items in public graph endpoints.

---

## 5. Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py -v
```
