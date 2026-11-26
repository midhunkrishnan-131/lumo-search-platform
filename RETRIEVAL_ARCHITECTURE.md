# LUMO Retrieval Architecture (Phase 29)

Phase 29 upgrades LUMO's existing `ClassicSearchEngine`, `SemanticSearchEngine`, and `HybridSearchOrchestrator` with:
- Unified Indexing & Duplicate Detection ([`engine.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/engine.py))
- Format-Aware Chunking ([`chunking.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/chunking.py))
- Cached Local Embedding Provider ([`embeddings.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/embeddings.py))
- Deterministic Query Processing ([`query_processor.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/query_processor.py))
- Modular Reranking & Explanations ([`reranker.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/reranker.py))
