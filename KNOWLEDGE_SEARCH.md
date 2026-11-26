# LUMO Knowledge Search & Recommendations (Phase 28)

- **Search (`POST /api/v1/knowledge/search`)**: Filters strictly by `owner_id`, `item_type`, `collection_id`, `tag`, `date_from`, `date_to`, and keyword match across `title`, `content`, and `summary`.
- **Recommendations (`GET /api/v1/knowledge/items/{id}/recommendations`)**: Explicitly separates `verified_relationships` (stored `KnowledgeRelationship` rows) from `suggested_connections` (`is_inferred: true`, based on shared tags or collection membership).
