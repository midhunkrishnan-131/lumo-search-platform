"""Core CRUD and orchestration service for LUMO Personal Workspace."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.graph.extractor import EntityExtractor
from app.models.graph import Entity
from app.models.workspace import (
    WorkspaceAnnotation,
    WorkspaceCollection,
    WorkspaceItem,
    WorkspaceItemTag,
    WorkspaceNote,
    WorkspaceNoteTag,
    WorkspaceTag,
)
from app.schemas.workspace import (
    WorkspaceAnnotationCreate,
    WorkspaceAnnotationResponse,
    WorkspaceAnnotationUpdate,
    WorkspaceCollectionCreate,
    WorkspaceCollectionResponse,
    WorkspaceCollectionUpdate,
    WorkspaceConnectionsResponse,
    WorkspaceDashboardResponse,
    WorkspaceItemCreate,
    WorkspaceItemListResponse,
    WorkspaceItemResponse,
    WorkspaceItemUpdate,
    WorkspaceNoteCreate,
    WorkspaceNoteResponse,
    WorkspaceNoteUpdate,
    WorkspaceStatsResponse,
    WorkspaceTagSchema,
)
from app.workspace.importer import compute_content_hash, _make_summary

logger = get_logger("workspace.service")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_tag_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", "-", raw.strip().lower())
    cleaned = re.sub(r"[^a-z0-9\-_]", "", cleaned)
    return cleaned[:64]


class WorkspaceService:
    """Manages personal workspace items, collections, notes, tags, annotations, and graph links."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Tags ---

    def _get_or_create_tags(self, tag_names: list[str]) -> list[WorkspaceTag]:
        tags: list[WorkspaceTag] = []
        seen: set[str] = set()
        for raw in tag_names:
            norm = normalize_tag_name(raw)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            tag = self.db.query(WorkspaceTag).filter(WorkspaceTag.name == norm).first()
            if not tag:
                tag = WorkspaceTag(name=norm, display_name=raw.strip()[:64] or norm)
                self.db.add(tag)
                self.db.flush()
            tags.append(tag)
        return tags

    def list_tags(self) -> list[WorkspaceTagSchema]:
        rows = self.db.query(WorkspaceTag).order_by(WorkspaceTag.name.asc()).all()
        return [WorkspaceTagSchema.model_validate(r) for r in rows]

    def create_tag(self, raw_name: str) -> WorkspaceTagSchema:
        tags = self._get_or_create_tags([raw_name])
        if not tags:
            raise ValueError("Tag name is invalid.")
        self.db.commit()
        return WorkspaceTagSchema.model_validate(tags[0])

    # --- Collections ---

    def _collection_to_response(self, col: WorkspaceCollection) -> WorkspaceCollectionResponse:
        item_cnt = (
            self.db.query(func.count(WorkspaceItem.id))
            .filter(WorkspaceItem.collection_id == col.id)
            .scalar()
            or 0
        )
        note_cnt = (
            self.db.query(func.count(WorkspaceNote.id))
            .filter(WorkspaceNote.collection_id == col.id)
            .scalar()
            or 0
        )
        return WorkspaceCollectionResponse(
            id=col.id,
            name=col.name,
            description=col.description,
            parent_id=col.parent_id,
            item_count=item_cnt,
            note_count=note_cnt,
            created_at=col.created_at,
            updated_at=col.updated_at,
        )

    def list_collections(self) -> list[WorkspaceCollectionResponse]:
        cols = self.db.query(WorkspaceCollection).order_by(WorkspaceCollection.name.asc()).all()
        return [self._collection_to_response(c) for c in cols]

    def get_collection(self, collection_id: str) -> WorkspaceCollectionResponse | None:
        col = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == collection_id).first()
        return self._collection_to_response(col) if col else None

    def create_collection(self, payload: WorkspaceCollectionCreate) -> WorkspaceCollectionResponse:
        if payload.parent_id:
            parent = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == payload.parent_id).first()
            if not parent:
                raise ValueError(f"Parent collection '{payload.parent_id}' not found.")

        col = WorkspaceCollection(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            parent_id=payload.parent_id,
        )
        self.db.add(col)
        self.db.commit()
        self.db.refresh(col)
        return self._collection_to_response(col)

    def update_collection(
        self, collection_id: str, payload: WorkspaceCollectionUpdate
    ) -> WorkspaceCollectionResponse | None:
        col = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == collection_id).first()
        if not col:
            return None
        if payload.name is not None:
            col.name = payload.name.strip()
        if payload.description is not None:
            col.description = payload.description.strip() or None
        if payload.parent_id is not None:
            if payload.parent_id == collection_id:
                raise ValueError("Collection cannot be its own parent.")
            col.parent_id = payload.parent_id or None
        col.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(col)
        return self._collection_to_response(col)

    def delete_collection(self, collection_id: str) -> bool:
        col = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == collection_id).first()
        if not col:
            return False
        self.db.delete(col)
        self.db.commit()
        return True

    # --- Items ---

    def _item_to_response(self, item: WorkspaceItem, is_duplicate: bool = False) -> WorkspaceItemResponse:
        tags = [link.tag.display_name for link in item.tag_links if link.tag]
        ann_count = (
            self.db.query(func.count(WorkspaceAnnotation.id))
            .filter(WorkspaceAnnotation.item_id == item.id)
            .scalar()
            or 0
        )
        return WorkspaceItemResponse(
            id=item.id,
            title=item.title,
            content=item.content,
            summary=item.summary,
            source_type=item.source_type,
            source_url=item.source_url,
            source_ref_id=item.source_ref_id,
            file_name=item.file_name,
            file_type=item.file_type,
            content_hash=item.content_hash,
            collection_id=item.collection_id,
            collection_name=item.collection.name if item.collection else None,
            tags=tags,
            metadata=item.metadata_json or {},
            annotation_count=ann_count,
            is_duplicate=is_duplicate,
            last_viewed_at=item.last_viewed_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def create_item(
        self,
        payload: WorkspaceItemCreate,
        file_name: str | None = None,
        file_type: str | None = None,
        content_hash_override: str | None = None,
    ) -> WorkspaceItemResponse:
        body_text = payload.content or payload.summary or payload.title
        c_hash = content_hash_override or compute_content_hash(f"{payload.source_url or ''}\n{body_text}")

        # Deduplicate by content_hash or source_url if identical
        existing = self.db.query(WorkspaceItem).filter(WorkspaceItem.content_hash == c_hash).first()
        if existing:
            if payload.collection_id and not existing.collection_id:
                existing.collection_id = payload.collection_id
            if payload.tags:
                self._sync_item_tags(existing, payload.tags, append_only=True)
            self.db.commit()
            self.db.refresh(existing)
            return self._item_to_response(existing, is_duplicate=True)

        if payload.collection_id:
            col = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == payload.collection_id).first()
            if not col:
                raise ValueError(f"Collection '{payload.collection_id}' not found.")

        item = WorkspaceItem(
            id=str(uuid.uuid4()),
            title=payload.title.strip(),
            content=payload.content,
            summary=payload.summary or _make_summary(payload.content),
            source_type=payload.source_type.strip(),
            source_url=payload.source_url,
            source_ref_id=payload.source_ref_id,
            file_name=file_name,
            file_type=file_type,
            content_hash=c_hash,
            collection_id=payload.collection_id,
            metadata_json=payload.metadata or {},
        )
        self.db.add(item)
        self.db.flush()

        if payload.tags:
            self._sync_item_tags(item, payload.tags, append_only=False)

        self.db.commit()
        self.db.refresh(item)
        return self._item_to_response(item, is_duplicate=False)

    def _sync_item_tags(self, item: WorkspaceItem, tag_names: list[str], append_only: bool = False) -> None:
        if not append_only:
            self.db.query(WorkspaceItemTag).filter(WorkspaceItemTag.item_id == item.id).delete()
            self.db.flush()

        tags = self._get_or_create_tags(tag_names)
        existing_ids = {
            link.tag_id
            for link in self.db.query(WorkspaceItemTag).filter(WorkspaceItemTag.item_id == item.id).all()
        }
        for t in tags:
            if t.id not in existing_ids:
                self.db.add(WorkspaceItemTag(item_id=item.id, tag_id=t.id))
        self.db.flush()

    def list_items(
        self,
        collection_id: str | None = None,
        source_type: str | None = None,
        tag: str | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> WorkspaceItemListResponse:
        q = self.db.query(WorkspaceItem)
        if collection_id:
            q = q.filter(WorkspaceItem.collection_id == collection_id)
        if source_type:
            q = q.filter(WorkspaceItem.source_type == source_type)
        if tag:
            norm_tag = normalize_tag_name(tag)
            q = q.filter(
                WorkspaceItem.tag_links.any(WorkspaceItemTag.tag.has(WorkspaceTag.name == norm_tag))
            )

        total = q.count()
        rows = q.order_by(WorkspaceItem.created_at.desc()).offset(offset).limit(limit).all()
        return WorkspaceItemListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._item_to_response(r) for r in rows],
        )

    def get_item(self, item_id: str, mark_viewed: bool = True) -> WorkspaceItemResponse | None:
        item = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == item_id).first()
        if not item:
            return None
        if mark_viewed:
            item.last_viewed_at = utc_now()
            self.db.commit()
            self.db.refresh(item)
        return self._item_to_response(item)

    def update_item(self, item_id: str, payload: WorkspaceItemUpdate) -> WorkspaceItemResponse | None:
        item = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == item_id).first()
        if not item:
            return None

        if payload.title is not None:
            item.title = payload.title.strip()
        if payload.content is not None:
            item.content = payload.content
            item.content_hash = compute_content_hash(f"{item.source_url or ''}\n{payload.content}")
        if payload.summary is not None:
            item.summary = payload.summary
        if payload.collection_id is not None:
            if payload.collection_id == "":
                item.collection_id = None
            else:
                col = self.db.query(WorkspaceCollection).filter(WorkspaceCollection.id == payload.collection_id).first()
                if not col:
                    raise ValueError(f"Collection '{payload.collection_id}' not found.")
                item.collection_id = payload.collection_id
        if payload.metadata is not None:
            item.metadata_json = payload.metadata
        if payload.tags is not None:
            self._sync_item_tags(item, payload.tags, append_only=False)

        item.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(item)
        return self._item_to_response(item)

    def delete_item(self, item_id: str) -> bool:
        item = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == item_id).first()
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        return True

    # --- Notes ---

    def _note_to_response(self, note: WorkspaceNote) -> WorkspaceNoteResponse:
        tags = [link.tag.display_name for link in note.tag_links if link.tag]
        return WorkspaceNoteResponse(
            id=note.id,
            title=note.title,
            content=note.content,
            collection_id=note.collection_id,
            linked_item_id=note.linked_item_id,
            linked_entity_id=note.linked_entity_id,
            linked_research_id=note.linked_research_id,
            tags=tags,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    def _sync_note_tags(self, note: WorkspaceNote, tag_names: list[str]) -> None:
        self.db.query(WorkspaceNoteTag).filter(WorkspaceNoteTag.note_id == note.id).delete()
        self.db.flush()
        for t in self._get_or_create_tags(tag_names):
            self.db.add(WorkspaceNoteTag(note_id=note.id, tag_id=t.id))
        self.db.flush()

    def list_notes(
        self,
        collection_id: str | None = None,
        linked_item_id: str | None = None,
        limit: int = 50,
    ) -> list[WorkspaceNoteResponse]:
        q = self.db.query(WorkspaceNote)
        if collection_id:
            q = q.filter(WorkspaceNote.collection_id == collection_id)
        if linked_item_id:
            q = q.filter(WorkspaceNote.linked_item_id == linked_item_id)
        rows = q.order_by(WorkspaceNote.updated_at.desc()).limit(limit).all()
        return [self._note_to_response(n) for n in rows]

    def get_note(self, note_id: str) -> WorkspaceNoteResponse | None:
        note = self.db.query(WorkspaceNote).filter(WorkspaceNote.id == note_id).first()
        return self._note_to_response(note) if note else None

    def create_note(self, payload: WorkspaceNoteCreate) -> WorkspaceNoteResponse:
        note = WorkspaceNote(
            id=str(uuid.uuid4()),
            title=payload.title.strip(),
            content=payload.content,
            collection_id=payload.collection_id or None,
            linked_item_id=payload.linked_item_id or None,
            linked_entity_id=payload.linked_entity_id or None,
            linked_research_id=payload.linked_research_id or None,
        )
        self.db.add(note)
        self.db.flush()
        if payload.tags:
            self._sync_note_tags(note, payload.tags)
        self.db.commit()
        self.db.refresh(note)
        return self._note_to_response(note)

    def update_note(self, note_id: str, payload: WorkspaceNoteUpdate) -> WorkspaceNoteResponse | None:
        note = self.db.query(WorkspaceNote).filter(WorkspaceNote.id == note_id).first()
        if not note:
            return None
        if payload.title is not None:
            note.title = payload.title.strip()
        if payload.content is not None:
            note.content = payload.content
        if payload.collection_id is not None:
            note.collection_id = payload.collection_id or None
        if payload.linked_item_id is not None:
            note.linked_item_id = payload.linked_item_id or None
        if payload.linked_entity_id is not None:
            note.linked_entity_id = payload.linked_entity_id or None
        if payload.linked_research_id is not None:
            note.linked_research_id = payload.linked_research_id or None
        if payload.tags is not None:
            self._sync_note_tags(note, payload.tags)
        note.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(note)
        return self._note_to_response(note)

    def delete_note(self, note_id: str) -> bool:
        note = self.db.query(WorkspaceNote).filter(WorkspaceNote.id == note_id).first()
        if not note:
            return False
        self.db.delete(note)
        self.db.commit()
        return True

    # --- Annotations ---

    def list_annotations(self, item_id: str) -> list[WorkspaceAnnotationResponse]:
        rows = (
            self.db.query(WorkspaceAnnotation)
            .filter(WorkspaceAnnotation.item_id == item_id)
            .order_by(WorkspaceAnnotation.start_offset.asc(), WorkspaceAnnotation.created_at.asc())
            .all()
        )
        return [WorkspaceAnnotationResponse.model_validate(a) for a in rows]

    def create_annotation(
        self, item_id: str, payload: WorkspaceAnnotationCreate
    ) -> WorkspaceAnnotationResponse | None:
        item = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == item_id).first()
        if not item:
            return None
        ann = WorkspaceAnnotation(
            id=str(uuid.uuid4()),
            item_id=item_id,
            selected_text=payload.selected_text,
            comment=payload.comment,
            start_offset=payload.start_offset,
            end_offset=payload.end_offset,
            linked_note_id=payload.linked_note_id,
        )
        self.db.add(ann)
        self.db.commit()
        self.db.refresh(ann)
        return WorkspaceAnnotationResponse.model_validate(ann)

    def update_annotation(
        self, annotation_id: str, payload: WorkspaceAnnotationUpdate
    ) -> WorkspaceAnnotationResponse | None:
        ann = self.db.query(WorkspaceAnnotation).filter(WorkspaceAnnotation.id == annotation_id).first()
        if not ann:
            return None
        if payload.comment is not None:
            ann.comment = payload.comment
        if payload.linked_note_id is not None:
            ann.linked_note_id = payload.linked_note_id or None
        ann.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(ann)
        return WorkspaceAnnotationResponse.model_validate(ann)

    def delete_annotation(self, annotation_id: str) -> bool:
        ann = self.db.query(WorkspaceAnnotation).filter(WorkspaceAnnotation.id == annotation_id).first()
        if not ann:
            return False
        self.db.delete(ann)
        self.db.commit()
        return True

    # --- Dashboard & Stats ---

    def get_stats(self) -> WorkspaceStatsResponse:
        total_items = self.db.query(func.count(WorkspaceItem.id)).scalar() or 0
        total_collections = self.db.query(func.count(WorkspaceCollection.id)).scalar() or 0
        total_notes = self.db.query(func.count(WorkspaceNote.id)).scalar() or 0
        total_tags = self.db.query(func.count(WorkspaceTag.id)).scalar() or 0
        total_annotations = self.db.query(func.count(WorkspaceAnnotation.id)).scalar() or 0
        by_type_rows = (
            self.db.query(WorkspaceItem.source_type, func.count(WorkspaceItem.id))
            .group_by(WorkspaceItem.source_type)
            .all()
        )
        return WorkspaceStatsResponse(
            total_items=total_items,
            total_collections=total_collections,
            total_notes=total_notes,
            total_tags=total_tags,
            total_annotations=total_annotations,
            items_by_type={stype: cnt for stype, cnt in by_type_rows},
        )

    def get_dashboard(self) -> WorkspaceDashboardResponse:
        recent_items = (
            self.db.query(WorkspaceItem)
            .order_by(WorkspaceItem.created_at.desc())
            .limit(8)
            .all()
        )
        recently_viewed = (
            self.db.query(WorkspaceItem)
            .filter(WorkspaceItem.last_viewed_at != None)  # noqa: E711
            .order_by(WorkspaceItem.last_viewed_at.desc())
            .limit(6)
            .all()
        )
        return WorkspaceDashboardResponse(
            stats=self.get_stats(),
            recent_items=[self._item_to_response(i) for i in recent_items],
            recently_viewed=[self._item_to_response(i) for i in recently_viewed],
            collections=self.list_collections(),
            recent_notes=self.list_notes(limit=6),
            tags=self.list_tags(),
        )

    # --- Knowledge Graph Connections (Private Isolation) ---

    def get_item_connections(self, item_id: str) -> WorkspaceConnectionsResponse | None:
        """Discover entities in item text and link to persisted Knowledge Graph + related workspace items."""
        item = self.db.query(WorkspaceItem).filter(WorkspaceItem.id == item_id).first()
        if not item:
            return None

        extractor = EntityExtractor()
        extracted = extractor.extract(item.content or "", title=item.title, max_entities=15)

        entities_out: list[dict[str, Any]] = []
        norm_names = {e.normalized_name for e in extracted}
        db_entities = (
            self.db.query(Entity).filter(Entity.normalized_name.in_(norm_names)).all()
            if norm_names
            else []
        )
        db_map = {e.normalized_name: e for e in db_entities}

        for ee in extracted:
            db_ent = db_map.get(ee.normalized_name)
            entities_out.append(
                {
                    "id": db_ent.id if db_ent else None,
                    "name": ee.name,
                    "type": ee.entity_type,
                    "in_knowledge_graph": db_ent is not None,
                    "snippet": ee.first_snippet,
                }
            )

        # Find other personal workspace items sharing any extracted entity name (strictly within workspace)
        related_items: list[WorkspaceItemResponse] = []
        if extracted:
            top_terms = [e.name for e in extracted[:4]]
            other_items = (
                self.db.query(WorkspaceItem)
                .filter(WorkspaceItem.id != item.id)
                .limit(30)
                .all()
            )
            for other in other_items:
                hay = f"{other.title} {other.content[:1500]}".lower()
                if any(term.lower() in hay for term in top_terms):
                    related_items.append(self._item_to_response(other))
                if len(related_items) >= 5:
                    break

        linked_notes = self.list_notes(linked_item_id=item.id, limit=10)
        return WorkspaceConnectionsResponse(
            item_id=item.id,
            entities=entities_out,
            related_items=related_items,
            linked_notes=linked_notes,
        )
