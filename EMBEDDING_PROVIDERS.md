# LUMO Embedding Providers (Phase 29)

`CachedLocalEmbeddingProvider` ([`embeddings.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/embeddings.py)) wraps `LocalEmbeddingService` with:
- Bounded LRU cache (`max_cache_size=1024`) keyed by `sha256(model_name | text)`.
- Strict dimension validation (`len(vec) == dimension`).
- Bounded retry without silently invoking paid external APIs.
