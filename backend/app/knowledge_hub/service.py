"""Personal Knowledge Hub service extending LUMO's Workspace storage with strict owner isolation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.ai.context import ContextBuilder
from app.models.knowledge_hub import (
    KnowledgeActivity,
    KnowledgeCollectionMeta,
    KnowledgeItemMeta,
    KnowledgeRelationship,
    VALID_KNOWLEDGE_ITEM_TYPES,
)
from app.models.workspace import (
    WorkspaceCollection,
    WorkspaceItem,
    WorkspaceItemTag,
    WorkspaceNote,
    WorkspaceNoteTag,
    WorkspaceTag,
)
from app.schemas.knowledge_hub import (
    KnowledgeCollectionCreate,
    KnowledgeCollectionUpdate,
    KnowledgeContextRequest,
    KnowledgeImportRequest,
    KnowledgeItemSaveRequest,
    KnowledgeNoteCreate,
    KnowledgeNoteUpdate,
    KnowledgeRelationshipCreate,
    KnowledgeSearchRequest,
)

_sanitizer = ContextBuilder()
MAX_IMPORT_ITEMS = 200


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_tag(name: str) -> str:
    return " ".join((name or "").strip().lower().split())[:64]


def _content_hash(item_type: str, title: str, url: str | None, content: str) -> str:
    seed = f"{item_type}|{title.strip().lower()}|{(url or '').strip().lower()}|{content.strip()[:500]}"
    return hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()


class KnowledgeHubService:
    """Persistent Knowledge Hub manager with owner isolation, deduplication, search, and context retrieval."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _log_activity(self, owner_id: str, category: str, entity_id: str, title: str, detail: str = "") -> None:
        self.db.add(
            KnowledgeActivity(
                id=str(uuid.uuid4()),
                owner_id=owner_id,
                category=category,
                entity_id=entity_id,
                title=title[:300],
                detail=detail[:500],
            )
        )

    def _get_or_create_tag(self, raw_name: str) -> WorkspaceTag | None:
        norm = _norm_tag(raw_name)
        if not norm:
            return None
        tag = self.db.query(WorkspaceTag).filter(WorkspaceTag.name == norm).first()
        if tag is None:
            tag = WorkspaceTag(name=norm, display_name=raw_name.strip()[:64] or norm)
            self.db.add(tag)
            self.db.flush()
        return tag

    def _serialize_item(self, item: WorkspaceItem, meta: KnowledgeItemMeta | None = None) -> dict[str, Any]:
        m = meta or self.db.query(KnowledgeItemMeta).filter(KnowledgeItemMeta.item_id == item.id).first()
        tags = [link.tag.display_name for link in (item.tag_links or []) if link.tag]
        return {
            "id": item.id,
            "owner_id": m.owner_id if m else "local",
            "item_type": m.item_type if m else item.source_type.upper(),
            "title": item.title,
            "description": item.summary or "",
            "content": item.content,
            "source_url": item.source_url,
            "source_ref_id": item.source_ref_id,
            "collection_id": item.collection_id,
            "tags": tags,
            "provenance": m.provenance_json if m else {},
            "related_refs": m.related_refs_json if m else [],
            "metadata_json": item.metadata_json or {},
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    # --- Collections ---

    def create_collection(self, payload: KnowledgeCollectionCreate, owner_id: str = "local") -> dict[str, Any]:
        col = WorkspaceCollection(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            description=payload.description,
        )
        self.db.add(col)
        self.db.flush()
        meta = KnowledgeCollectionMeta(
            collection_id=col.id,
            owner_id=owner_id,
            icon=payload.icon,
            tags_json=[_norm_tag(t) for t in payload.tags if _norm_tag(t)],
        )
        self.db.add(meta)
        self._log_activity(owner_id, "collection_updated", col.id, f"Created collection '{col.name}'")
        self.db.commit()
        self.db.refresh(col)
        return self._serialize_collection(col, meta)

    def _serialize_collection(self, col: WorkspaceCollection, meta: KnowledgeCollectionMeta | None = None) -> dict[str, Any]:
        m = meta or self.db.query(KnowledgeCollectionMeta).filter(KnowledgeCollectionMeta.collection_id == col.id).first()
        item_count = (
            self.db.query(WorkspaceItem)
            .join(KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id)
            .filter(WorkspaceItem.collection_id == col.id, KnowledgeItemMeta.owner_id == (m.owner_id if m else "local"))
            .count()
        )
        return {
            "id": col.id,
            "owner_id": m.owner_id if m else "local",
            "name": col.name,
            "description": col.description,
            "icon": m.icon if m else "folder",
            "tags": m.tags_json if m else [],
            "item_count": item_count,
            "created_at": col.created_at.isoformat() if col.created_at else None,
            "updated_at": col.updated_at.isoformat() if col.updated_at else None,
        }

    def list_collections(self, owner_id: str = "local") -> list[dict[str, Any]]:
        rows = (
            self.db.query(WorkspaceCollection, KnowledgeCollectionMeta)
            .join(KnowledgeCollectionMeta, KnowledgeCollectionMeta.collection_id == WorkspaceCollection.id)
            .filter(KnowledgeCollectionMeta.owner_id == owner_id)
            .order_by(WorkspaceCollection.updated_at.desc())
            .all()
        )
        return [self._serialize_collection(c, m) for c, m in rows]

    def _get_owned_collection(self, collection_id: str, owner_id: str) -> tuple[WorkspaceCollection, KnowledgeCollectionMeta]:
        row = (
            self.db.query(WorkspaceCollection, KnowledgeCollectionMeta)
            .join(KnowledgeCollectionMeta, KnowledgeCollectionMeta.collection_id == WorkspaceCollection.id)
            .filter(WorkspaceCollection.id == collection_id, KnowledgeCollectionMeta.owner_id == owner_id)
            .first()
        )
        if not row:
            raise ValueError("Collection not found.")
        return row

    def update_collection(self, collection_id: str, payload: KnowledgeCollectionUpdate, owner_id: str = "local") -> dict[str, Any]:
        col, meta = self._get_owned_collection(collection_id, owner_id)
        if payload.name is not None:
            col.name = payload.name.strip()
        if payload.description is not None:
            col.description = payload.description
        if payload.icon is not None:
            meta.icon = payload.icon
        if payload.tags is not None:
            meta.tags_json = [_norm_tag(t) for t in payload.tags if _norm_tag(t)]
        col.updated_at = _utc_now()
        self._log_activity(owner_id, "collection_updated", col.id, f"Updated collection '{col.name}'")
        self.db.commit()
        return self._serialize_collection(col, meta)

    def delete_collection(self, collection_id: str, owner_id: str = "local") -> bool:
        row = (
            self.db.query(WorkspaceCollection, KnowledgeCollectionMeta)
            .join(KnowledgeCollectionMeta, KnowledgeCollectionMeta.collection_id == WorkspaceCollection.id)
            .filter(WorkspaceCollection.id == collection_id, KnowledgeCollectionMeta.owner_id == owner_id)
            .first()
        )
        if not row:
            return False
        col, _ = row
        # Preserve underlying WorkspaceItems by unlinking collection_id before deleting collection
        for it in self.db.query(WorkspaceItem).filter(WorkspaceItem.collection_id == col.id).all():
            it.collection_id = None
        self.db.delete(col)
        self.db.commit()
        return True

    # --- Save & Items ---

    def save_item(self, payload: KnowledgeItemSaveRequest, owner_id: str = "local") -> dict[str, Any]:
        itype = payload.item_type.strip().upper()
        if itype not in VALID_KNOWLEDGE_ITEM_TYPES:
            raise ValueError(f"Unsupported item_type '{payload.item_type}'.")

        col_id = payload.collection_id
        if col_id:
            self._get_owned_collection(col_id, owner_id)
        elif payload.new_collection_name and payload.new_collection_name.strip():
            created_col = self.create_collection(
                KnowledgeCollectionCreate(name=payload.new_collection_name.strip()),
                owner_id=owner_id,
            )
            col_id = created_col["id"]

        chash = _content_hash(itype, payload.title, payload.source_url, payload.content or payload.description)
        existing = (
            self.db.query(WorkspaceItem, KnowledgeItemMeta)
            .join(KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id)
            .filter(WorkspaceItem.content_hash == chash, KnowledgeItemMeta.owner_id == owner_id)
            .first()
        )
        if existing:
            out = self._serialize_item(existing[0], existing[1])
            out["deduplicated"] = True
            return out

        item = WorkspaceItem(
            id=str(uuid.uuid4()),
            title=payload.title.strip(),
            content=payload.content or payload.description,
            summary=payload.description[:1000] if payload.description else None,
            source_type=itype.lower(),
            source_url=payload.source_url,
            source_ref_id=payload.source_ref_id,
            content_hash=chash,
            collection_id=col_id,
            metadata_json=payload.metadata_json,
        )
        self.db.add(item)
        self.db.flush()

        meta = KnowledgeItemMeta(
            item_id=item.id,
            owner_id=owner_id,
            item_type=itype,
            provenance_json=payload.provenance,
        )
        self.db.add(meta)

        for raw_t in payload.tags:
            t = self._get_or_create_tag(raw_t)
            if t is not None:
                self.db.add(WorkspaceItemTag(item_id=item.id, tag_id=t.id))

        if payload.note and payload.note.strip():
            self.db.add(
                WorkspaceNote(
                    id=str(uuid.uuid4()),
                    title=f"Note on {item.title[:120]}",
                    content=payload.note.strip(),
                    collection_id=col_id,
                    linked_item_id=item.id,
                )
            )

        self._log_activity(owner_id, "item_saved", item.id, item.title, f"Saved {itype}")
        self.db.commit()
        self.db.refresh(item)
        out = self._serialize_item(item, meta)
        out["deduplicated"] = False
        return out

    def get_item(self, item_id: str, owner_id: str = "local") -> dict[str, Any]:
        row = (
            self.db.query(WorkspaceItem, KnowledgeItemMeta)
            .join(KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id)
            .filter(WorkspaceItem.id == item_id, KnowledgeItemMeta.owner_id == owner_id)
            .first()
        )
        if not row:
            raise ValueError("Knowledge item not found.")
        return self._serialize_item(row[0], row[1])

    def move_item(self, item_id: str, collection_id: str | None, owner_id: str = "local") -> dict[str, Any]:
        row = (
            self.db.query(WorkspaceItem, KnowledgeItemMeta)
            .join(KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id)
            .filter(WorkspaceItem.id == item_id, KnowledgeItemMeta.owner_id == owner_id)
            .first()
        )
        if not row:
            raise ValueError("Knowledge item not found.")
        if collection_id is not None:
            self._get_owned_collection(collection_id, owner_id)
        row[0].collection_id = collection_id
        row[0].updated_at = _utc_now()
        self.db.commit()
        return self._serialize_item(row[0], row[1])

    def delete_item(self, item_id: str, owner_id: str = "local") -> bool:
        row = (
            self.db.query(WorkspaceItem, KnowledgeItemMeta)
            .join(KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id)
            .filter(WorkspaceItem.id == item_id, KnowledgeItemMeta.owner_id == owner_id)
            .first()
        )
        if not row:
            return False
        self.db.delete(row[0])
        self.db.commit()
        return True

    # --- Search ---

    def search_knowledge(self, payload: KnowledgeSearchRequest, owner_id: str = "local") -> list[dict[str, Any]]:
        q = self.db.query(WorkspaceItem, KnowledgeItemMeta).join(
            KnowledgeItemMeta, KnowledgeItemMeta.item_id == WorkspaceItem.id
        ).filter(KnowledgeItemMeta.owner_id == owner_id)

        if payload.item_type:
            q = q.filter(KnowledgeItemMeta.item_type == payload.item_type.strip().upper())
        if payload.collection_id:
            q = q.filter(WorkspaceItem.collection_id == payload.collection_id)
        if payload.date_from:
            q = q.filter(WorkspaceItem.created_at >= payload.date_from)
        if payload.date_to:
            q = q.filter(WorkspaceItem.created_at <= payload.date_to)
        if payload.query.strip():
            like = f"%{payload.query.strip()}%"
            q = q.filter(
                (WorkspaceItem.title.ilike(like))
                | (WorkspaceItem.content.ilike(like))
                | (WorkspaceItem.summary.ilike(like))
            )
        rows = q.order_by(WorkspaceItem.updated_at.desc()).limit(payload.limit).all()
        items = [self._serialize_item(it, m) for it, m in rows]
        if payload.tag:
            want = _norm_tag(payload.tag)
            items = [it for it in items if any(_norm_tag(t) == want for t in it["tags"])]
        return items

    # --- Notes ---

    def _owned_note_ids(self, owner_id: str) -> set[str]:
        rows = (
            self.db.query(KnowledgeActivity.entity_id)
            .filter(KnowledgeActivity.owner_id == owner_id, KnowledgeActivity.category == "note_created")
            .all()
        )
        return {r[0] for r in rows}

    def create_note(self, payload: KnowledgeNoteCreate, owner_id: str = "local") -> dict[str, Any]:
        if payload.collection_id:
            self._get_owned_collection(payload.collection_id, owner_id)
        if payload.linked_item_id:
            self.get_item(payload.linked_item_id, owner_id=owner_id)
        note = WorkspaceNote(
            id=str(uuid.uuid4()),
            title=payload.title.strip(),
            content=payload.content,
            collection_id=payload.collection_id,
            linked_item_id=payload.linked_item_id,
        )
        self.db.add(note)
        self.db.flush()
        for raw_t in payload.tags:
            t = self._get_or_create_tag(raw_t)
            if t is not None:
                self.db.add(WorkspaceNoteTag(note_id=note.id, tag_id=t.id))
        self._log_activity(owner_id, "note_created", note.id, note.title)
        self.db.commit()
        return self._serialize_note(note, owner_id)

    def _serialize_note(self, note: WorkspaceNote, owner_id: str) -> dict[str, Any]:
        tags = [link.tag.display_name for link in (note.tag_links or []) if link.tag]
        return {
            "id": note.id,
            "owner_id": owner_id,
            "title": note.title,
            "content": note.content,
            "collection_id": note.collection_id,
            "linked_item_id": note.linked_item_id,
            "tags": tags,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        }

    def list_notes(self, owner_id: str = "local", q: str | None = None) -> list[dict[str, Any]]:
        ids = self._owned_note_ids(owner_id)
        if not ids:
            return []
        query = self.db.query(WorkspaceNote).filter(WorkspaceNote.id.in_(ids))
        if q and q.strip():
            like = f"%{q.strip()}%"
            query = query.filter((WorkspaceNote.title.ilike(like)) | (WorkspaceNote.content.ilike(like)))
        return [self._serialize_note(n, owner_id) for n in query.order_by(WorkspaceNote.updated_at.desc()).all()]

    def update_note(self, note_id: str, payload: KnowledgeNoteUpdate, owner_id: str = "local") -> dict[str, Any]:
        if note_id not in self._owned_note_ids(owner_id):
            raise ValueError("Note not found.")
        note = self.db.query(WorkspaceNote).filter(WorkspaceNote.id == note_id).first()
        if not note:
            raise ValueError("Note not found.")
        if payload.title is not None:
            note.title = payload.title.strip()
        if payload.content is not None:
            note.content = payload.content
        if payload.collection_id is not None:
            self._get_owned_collection(payload.collection_id, owner_id)
            note.collection_id = payload.collection_id
        note.updated_at = _utc_now()
        self.db.commit()
        return self._serialize_note(note, owner_id)

    def delete_note(self, note_id: str, owner_id: str = "local") -> bool:
        if note_id not in self._owned_note_ids(owner_id):
            return False
        note = self.db.query(WorkspaceNote).filter(WorkspaceNote.id == note_id).first()
        if not note:
            return False
        self.db.delete(note)
        self.db.commit()
        return True

    # --- Tags ---

    def list_tags(self, owner_id: str = "local") -> list[dict[str, Any]]:
        items = self.search_knowledge(KnowledgeSearchRequest(limit=100), owner_id=owner_id)
        counts: dict[str, int] = {}
        for it in items:
            for t in it["tags"]:
                counts[t] = counts.get(t, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(counts.items())]

    def rename_tag(self, old_name: str, new_name: str) -> dict[str, str]:
        old_norm = _norm_tag(old_name)
        new_norm = _norm_tag(new_name)
        if not old_norm or not new_norm:
            raise ValueError("Tag name cannot be empty.")
        tag = self.db.query(WorkspaceTag).filter(WorkspaceTag.name == old_norm).first()
        if not tag:
            raise ValueError("Tag not found.")
        existing_new = self.db.query(WorkspaceTag).filter(WorkspaceTag.name == new_norm).first()
        if existing_new and existing_new.id != tag.id:
            raise ValueError("Target tag name already exists.")
        tag.name = new_norm
        tag.display_name = new_name.strip()[:64]
        self.db.commit()
        return {"name": tag.name, "display_name": tag.display_name}

    # --- Relationships & Recommendations ---

    def link_items(self, payload: KnowledgeRelationshipCreate, owner_id: str = "local") -> dict[str, Any]:
        self.get_item(payload.source_item_id, owner_id=owner_id)
        self.get_item(payload.target_item_id, owner_id=owner_id)
        rel = KnowledgeRelationship(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            source_item_id=payload.source_item_id,
            target_item_id=payload.target_item_id,
            relationship_type=payload.relationship_type.strip().upper(),
            evidence=payload.evidence,
            is_inferred=False,
        )
        self.db.add(rel)
        self._log_activity(owner_id, "relationship_linked", rel.id, f"{rel.relationship_type}")
        self.db.commit()
        return {
            "id": rel.id,
            "source_item_id": rel.source_item_id,
            "target_item_id": rel.target_item_id,
            "relationship_type": rel.relationship_type,
            "evidence": rel.evidence,
            "is_inferred": rel.is_inferred,
        }

    def list_relationships(self, owner_id: str = "local") -> list[dict[str, Any]]:
        rows = (
            self.db.query(KnowledgeRelationship)
            .filter(KnowledgeRelationship.owner_id == owner_id)
            .order_by(KnowledgeRelationship.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "source_item_id": r.source_item_id,
                "target_item_id": r.target_item_id,
                "relationship_type": r.relationship_type,
                "evidence": r.evidence,
                "is_inferred": r.is_inferred,
            }
            for r in rows
        ]

    def recommend_connections(self, item_id: str, owner_id: str = "local") -> dict[str, Any]:
        target = self.get_item(item_id, owner_id=owner_id)
        verified = [
            r for r in self.list_relationships(owner_id=owner_id)
            if r["source_item_id"] == item_id or r["target_item_id"] == item_id
        ]
        target_tags = {_norm_tag(t) for t in target["tags"]}
        similar: list[dict[str, Any]] = []
        for other in self.search_knowledge(KnowledgeSearchRequest(limit=50), owner_id=owner_id):
            if other["id"] == item_id:
                continue
            shared_tags = target_tags & {_norm_tag(t) for t in other["tags"]}
            if shared_tags or (target["collection_id"] and target["collection_id"] == other["collection_id"]):
                similar.append({
                    "item_id": other["id"],
                    "title": other["title"],
                    "reason": "shared_tags" if shared_tags else "same_collection",
                    "shared_tags": sorted(shared_tags),
                    "is_inferred": True,
                })
        return {
            "item_id": item_id,
            "verified_relationships": verified,
            "suggested_connections": similar[:10],
        }

    # --- Timeline, Dashboard & Context ---

    def get_timeline(self, owner_id: str = "local", category: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        q = self.db.query(KnowledgeActivity).filter(KnowledgeActivity.owner_id == owner_id)
        if category:
            q = q.filter(KnowledgeActivity.category == category)
        rows = q.order_by(KnowledgeActivity.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "category": r.category,
                "entity_id": r.entity_id,
                "title": r.title,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def get_dashboard(self, owner_id: str = "local") -> dict[str, Any]:
        return {
            "collections": self.list_collections(owner_id=owner_id),
            "recent_items": self.search_knowledge(KnowledgeSearchRequest(limit=20), owner_id=owner_id),
            "notes": self.list_notes(owner_id=owner_id)[:15],
            "tags": self.list_tags(owner_id=owner_id),
            "timeline": self.get_timeline(owner_id=owner_id, limit=20),
        }

    def build_knowledge_context(self, payload: KnowledgeContextRequest, owner_id: str = "local") -> dict[str, Any]:
        """Retrieve user-selected Knowledge Hub items safely with prompt-injection sanitization."""
        selected: list[dict[str, Any]] = []
        if payload.item_ids:
            for iid in payload.item_ids[:20]:
                try:
                    selected.append(self.get_item(iid, owner_id=owner_id))
                except ValueError:
                    continue
        elif payload.collection_id or payload.query:
            selected = self.search_knowledge(
                KnowledgeSearchRequest(
                    query=payload.query,
                    collection_id=payload.collection_id,
                    limit=10,
                ),
                owner_id=owner_id,
            )

        blocks: list[str] = []
        attributions: list[dict[str, Any]] = []
        used = 0
        for idx, it in enumerate(selected, start=1):
            remaining = payload.max_chars - used
            if remaining <= 0:
                break
            safe_txt = _sanitizer._sanitize_for_prompt((it["content"] or it["description"] or "")[:remaining])
            block = f"[K{idx}] {it['title']} ({it['item_type']}): {safe_txt}"
            blocks.append(block[:remaining])
            used += len(block)
            attributions.append({
                "context_id": f"K{idx}",
                "item_id": it["id"],
                "title": it["title"],
                "source_url": it["source_url"],
            })

        return {
            "context_text": "\n\n".join(blocks),
            "attributions": attributions,
            "char_count": sum(len(b) for b in blocks),
            "untrusted_content_notice": "Saved external knowledge is sanitized and treated as untrusted data.",
        }

    # --- Import & Export ---

    def export_knowledge(self, owner_id: str = "local", fmt: str = "json", collection_id: str | None = None) -> tuple[str, str]:
        items = self.search_knowledge(
            KnowledgeSearchRequest(collection_id=collection_id, limit=100),
            owner_id=owner_id,
        )
        cols = self.list_collections(owner_id=owner_id)
        notes = self.list_notes(owner_id=owner_id)
        if fmt.lower() == "markdown":
            lines = ["# LUMO Personal Knowledge Hub Export", ""]
            lines.append(f"Collections: {len(cols)} | Items: {len(items)} | Notes: {len(notes)}")
            lines.append("")
            for it in items:
                lines.append(f"## [{it['item_type']}] {it['title']}")
                if it["source_url"]:
                    lines.append(f"- Source: {it['source_url']}")
                if it["tags"]:
                    lines.append(f"- Tags: {', '.join(it['tags'])}")
                lines.append("")
                lines.append(it["content"] or it["description"] or "")
                lines.append("")
            return "\n".join(lines), "text/markdown"
        return json.dumps({"collections": cols, "items": items, "notes": notes}, indent=2), "application/json"

    def import_knowledge(self, payload: KnowledgeImportRequest, owner_id: str = "local") -> dict[str, int]:
        if len(payload.items) > MAX_IMPORT_ITEMS:
            raise ValueError(f"Import exceeds maximum {MAX_IMPORT_ITEMS} items.")
        col_map: dict[str, str] = {}
        cols_created = 0
        for c in payload.collections[:50]:
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            created = self.create_collection(
                KnowledgeCollectionCreate(
                    name=name,
                    description=c.get("description"),
                    icon=str(c.get("icon") or "folder")[:32],
                ),
                owner_id=owner_id,
            )
            if c.get("id"):
                col_map[str(c["id"])] = created["id"]
            cols_created += 1

        saved = 0
        deduped = 0
        for it in payload.items:
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            itype = str(it.get("item_type") or "SOURCE").upper()
            if itype not in VALID_KNOWLEDGE_ITEM_TYPES:
                itype = "SOURCE"
            res = self.save_item(
                KnowledgeItemSaveRequest(
                    item_type=itype,
                    title=title,
                    description=str(it.get("description") or ""),
                    content=str(it.get("content") or ""),
                    source_url=it.get("source_url"),
                    collection_id=col_map.get(str(it.get("collection_id") or "")),
                    tags=[str(t) for t in (it.get("tags") or [])],
                ),
                owner_id=owner_id,
            )
            if res.get("deduplicated"):
                deduped += 1
            else:
                saved += 1

        self._log_activity(owner_id, "import_completed", owner_id, f"Imported {saved} items ({deduped} duplicates skipped)")
        self.db.commit()
        return {"collections_created": cols_created, "items_saved": saved, "duplicates_skipped": deduped}
