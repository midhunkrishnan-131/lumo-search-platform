# LUMO Hybrid Retrieval & Query Processing (Phase 29)

`UnifiedRetrievalEngine.retrieve()` combines:
1. `process_query()` (normalization, intent classification, key-term extraction, expansion, and sub-query decomposition while preserving `original_query`).
2. Core retrieval (`classic`, `semantic`, or `hybrid` RRF) + metadata filters (`domain`, `language`, `content_type`).
3. Owner-isolated Knowledge Hub retrieval (`include_knowledge_hub=true`).
4. `rerank_candidates()` with transparent `explanations` (`Keyword match`, `Semantic similarity`, `Metadata match`, `Knowledge Hub`, `Reranking`).
