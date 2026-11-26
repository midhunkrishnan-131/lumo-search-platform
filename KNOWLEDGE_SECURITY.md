# LUMO Knowledge Hub Security (Phase 28)

- **Owner Isolation**: All collections, items, notes, relationships, timeline events, exports, and context queries are strictly filtered by `owner_id` (`X-LUMO-Owner`).
- **Permissions**: Developer API keys enforce `workspace:read` for reads/searches/exports/context and `workspace:write` for mutations.
- **Prompt Injection Defense**: Context retrieval sanitizes saved external text via `ContextBuilder._sanitize_for_prompt()` and labels it untrusted.
- **XSS Safety**: Frontend [`knowledge-hub.js`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/js/knowledge-hub.js) escapes all rendered strings with `escapeHtml()`.
