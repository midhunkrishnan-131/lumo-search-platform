"""Semantic search engine with query embedding, Qdrant retrieval, and document aggregation."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.search.engine import SearchResult, SearchResultSet
from app.search.snippet import generate_snippet
from app.semantic.embedding import LocalEmbeddingService, embedding_service as default_embedder
from app.semantic.vector_store import QdrantVectorStore, vector_store as default_store

logger = get_logger("semantic.search")


class SemanticSearchEngine:
    """Performs vector similarity search in Qdrant and aggregates results at document level."""

    def __init__(
        self,
        db: Session,
        vector_store: QdrantVectorStore | None = None,
        embedder: LocalEmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.store = vector_store or default_store
        self.embedder = embedder or default_embedder

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 8,
        domain: str | None = None,
        language: str | None = None,
    ) -> SearchResultSet:
        """Execute semantic search over indexed document vectors.

        Args:
            query: User search query.
            page: 1-indexed page number.
            per_page: Number of results per page.
            domain: Optional domain filter.
            language: Optional language filter.

        Returns:
            SearchResultSet with document-aggregated semantic results.
        """
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page

        clean_query = self._normalize_query(query)
        if not clean_query:
            return SearchResultSet(
                query=query,
                mode="semantic",
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                results=[],
            )

        # 1. Embed search query
        query_vector = self.embedder.embed_query(clean_query)

        # 2. Retrieve nearest vector chunks (fetch multiple chunks to allow aggregation)
        retrieval_limit = max(per_page * 5, 25)
        raw_matches = self.store.search_vectors(
            query_vector=query_vector,
            limit=retrieval_limit,
            domain_filter=domain,
        )

        if not raw_matches:
            return SearchResultSet(
                query=query,
                mode="semantic",
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                results=[],
            )

        # 3. Document-level aggregation (deduplicate multiple chunks from same document)
        doc_best_chunk: dict[str, tuple[float, str]] = {}  # doc_id -> (best_score, best_text)
        for match in raw_matches:
            payload = match.get("payload", {})
            doc_id = payload.get("document_id")
            if not doc_id:
                continue

            score = float(match.get("score", 0.0))
            chunk_text = payload.get("chunk_text", "")

            if doc_id not in doc_best_chunk or score > doc_best_chunk[doc_id][0]:
                doc_best_chunk[doc_id] = (score, chunk_text)

        if not doc_best_chunk:
            return SearchResultSet(
                query=query,
                mode="semantic",
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                results=[],
            )

        # 4. Fetch canonical document records from PostgreSQL
        doc_ids = list(doc_best_chunk.keys())
        query_obj = self.db.query(Document).filter(
            Document.id.in_(doc_ids),
            Document.is_duplicate.is_(False),
        )

        if domain:
            query_obj = query_obj.filter(Document.domain == domain.lower())
        if language:
            query_obj = query_obj.filter(Document.language.ilike(f"{language}%"))

        db_docs = {d.id: d for d in query_obj.all()}

        # 5. Order documents by highest semantic similarity score
        scored_docs: list[tuple[Document, float, str]] = []
        for doc_id, (score, chunk_text) in doc_best_chunk.items():
            if doc_id in db_docs:
                scored_docs.append((db_docs[doc_id], score, chunk_text))

        scored_docs.sort(key=lambda item: item[1], reverse=True)

        total = len(scored_docs)
        total_pages = max(1, (total + per_page - 1) // per_page)
        paginated = scored_docs[offset : offset + per_page]

        # 6. Format search results with contextual snippets
        results: list[SearchResult] = []
        for doc, score, chunk_text in paginated:
            domain_val = doc.domain or (urlparse(doc.url).netloc.lower() if doc.url else "")
            snippet_source = chunk_text or doc.description or doc.main_content or ""
            snippet = generate_snippet(snippet_source, clean_query)

            results.append(
                SearchResult(
                    id=doc.id,
                    title=doc.title or doc.url,
                    url=doc.url,
                    domain=domain_val,
                    description=doc.description or "",
                    snippet=snippet,
                    score=round(score, 3),
                    published_at=doc.published_date or (doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""),
                    canonical_url=doc.canonical_url,
                    language=doc.language,
                )
            )

        return SearchResultSet(
            query=query,
            mode="semantic",
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            results=results,
        )

    def _normalize_query(self, query: str) -> str:
        if not query:
            return ""
        cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", query)
        return re.sub(r"\s+", " ", cleaned).strip()[:400]
