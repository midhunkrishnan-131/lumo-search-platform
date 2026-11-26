# LUMO Chunking Strategies (Phase 29)

Implemented in [`chunking.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/chunking.py):
- `pdf`: Splits on form-feed `\f` or `[Page N]` markers, preserving `page_number`.
- `markdown` / `md`: Splits on `#`–`###` headings, preserving `section`.
- `text`: Paragraph and sentence-aware splitting with configurable `chunk_size`, `chunk_overlap`, and `approx_tokens`.
