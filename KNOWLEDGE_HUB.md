# LUMO Personal Knowledge Hub (Phase 28)

The Personal Knowledge Hub ([`knowledge-hub.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/knowledge-hub.html)) extends LUMO's Phase 14 workspace tables (`workspace_collections`, `workspace_items`, `workspace_notes`, `workspace_tags`) with owner isolation, provenance, relationships, and timeline tracking:
- **Models**: [`knowledge_hub.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/models/knowledge_hub.py) (`KnowledgeItemMeta`, `KnowledgeCollectionMeta`, `KnowledgeRelationship`, `KnowledgeActivity`).
- **Service**: [`service.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/knowledge_hub/service.py).
- **Non-destructive Collections**: Deleting a collection unlinks `collection_id` on items without deleting underlying saved items.
