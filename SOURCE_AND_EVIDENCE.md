# LUMO Source & Evidence Management (Phase 27)

Implemented in [`context.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/workflows/context.py).

- `make_source_record()` normalizes `source_id`, `url`, `title`, `domain`, `source_type`, `retrieved_at`, `module`, `relevance`, `citation_id`, sanitized `excerpt`, and `verification_status`.
- `deduplicate_sources()` removes duplicate URLs/source IDs while preserving the highest relevance and `verified` status.
- `detect_disagreements_and_gaps()` flags Guardian-blocked URLs (`blocked_source`), unsupported citation keys (`unsupported_citation`), and missing source records (`missing_sources`).
