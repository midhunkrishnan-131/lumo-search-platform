# LUMO Indexing Engine & Duplicate Detection (Phase 29)

`UnifiedRetrievalEngine.index_content()` persists `IndexedRecord` entries (`indexed_records` table) with:
- URL normalization (`normalize_url`), SHA-256 `content_hash`, and 3-gram shingle signatures (`shingle_sig`).
- Non-destructive duplicate flagging (`status="duplicate_flagged"`, `duplicate_of_id` set) for exact hash, normalized URL, or Jaccard similarity `>= 0.85`.
