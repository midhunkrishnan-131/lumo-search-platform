"""Semantic indexing pipeline coordinating chunking, embedding, and vector storage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.semantic.chunker import chunk_document
from app.semantic.embedding import LocalEmbeddingService, embedding_service as default_embedder
from app.semantic.vector_store import QdrantVectorStore, vector_store as default_store

logger = get_logger("semantic.indexer")


class SemanticIndexer:
    """Coordinates document chunking, embedding generation, and vector database persistence."""

    def __init__(
        self,
        vector_store: QdrantVectorStore | None = None,
        embedder: LocalEmbeddingService | None = None,
    ) -> None:
        self.store = vector_store or default_store
        self.embedder = embedder or default_embedder

    def index_document(self, document_id: str, db: Session) -> bool:
        """Index a single document into the vector store.

        Args:
            document_id: UUID of the document to index.
            db: Database session.

        Returns:
            True if indexing succeeded, False otherwise.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("Document %s not found for semantic indexing", document_id)
            return False

        if doc.is_duplicate:
            doc.semantic_status = "skipped"
            doc.semantic_error = "Document is duplicate of primary document."
            db.commit()
            return False

        doc.semantic_status = "processing"
        db.commit()

        try:
            # 1. Chunk document
            chunks = chunk_document(doc)
            if not chunks:
                doc.semantic_status = "skipped"
                doc.indexed_chunks_count = 0
                doc.semantic_error = "No chunkable text content found."
                db.commit()
                return True

            # 2. Generate embeddings
            texts = [c.chunk_text for c in chunks]
            vectors = self.embedder.embed_texts(texts)

            # 3. Format points
            points = [
                {
                    "id": c.chunk_id,
                    "vector": vec,
                    "payload": {
                        "document_id": c.document_id,
                        "chunk_id": c.chunk_id,
                        "chunk_position": c.chunk_position,
                        "chunk_text": c.chunk_text,
                        "title": c.title,
                        "url": c.url,
                        "domain": c.domain,
                        "content_hash": c.content_hash,
                    },
                }
                for c, vec in zip(chunks, vectors)
            ]

            # 4. Upsert into vector store
            self.store.ensure_collection()
            upsert_ok = self.store.upsert_points(points)
            if not upsert_ok:
                raise RuntimeError("Failed to upsert points into vector store")

            # 5. Update document status
            doc.semantic_status = "indexed"
            doc.indexed_chunks_count = len(chunks)
            doc.semantic_indexed_at = datetime.now(timezone.utc)
            doc.semantic_error = None
            db.commit()
            logger.info("Indexed document %s into %d vector chunks", doc.id, len(chunks))
            return True

        except Exception as exc:
            logger.error("Semantic indexing failed for document %s: %s", doc.id, exc, exc_info=True)
            doc.semantic_status = "failed"
            doc.semantic_error = str(exc)
            db.commit()
            return False

    def reindex_document(self, document_id: str, db: Session) -> bool:
        """Remove existing vectors and re-chunk/re-embed the document."""
        self.store.delete_document_vectors(document_id)
        return self.index_document(document_id, db)

    def delete_document_vectors(self, document_id: str, db: Session) -> bool:
        """Remove document vectors and mark status pending/skipped."""
        self.store.delete_document_vectors(document_id)
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.semantic_status = "pending"
            doc.indexed_chunks_count = 0
            doc.semantic_indexed_at = None
            db.commit()
        return True

    def index_pending_documents(self, db: Session, limit: int = 10) -> int:
        """Find pending or failed non-duplicate documents and index them."""
        docs = (
            db.query(Document)
            .filter(
                Document.semantic_status.in_(["pending", "failed"]),
                Document.is_duplicate.is_(False),
            )
            .limit(limit)
            .all()
        )

        indexed_count = 0
        for doc in docs:
            if self.index_document(doc.id, db):
                indexed_count += 1

        return indexed_count


# Singleton indexer
semantic_indexer = SemanticIndexer()
