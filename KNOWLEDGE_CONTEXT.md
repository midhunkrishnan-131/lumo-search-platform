# LUMO Knowledge Context in Research & Workflows (Phase 28)

- **User-Controlled Inclusion**: Workflows only include Knowledge Hub context when `inputs.knowledge_collection_id` or `inputs.knowledge_item_ids` is explicitly provided by the user.
- **Endpoint**: `POST /api/v1/knowledge/context` retrieves owner-scoped items, enforces `max_chars` (default `6000`), attaches `attributions` (`[K1]`, `[K2]`), and sanitizes all text via `ContextBuilder._sanitize_for_prompt()`.
