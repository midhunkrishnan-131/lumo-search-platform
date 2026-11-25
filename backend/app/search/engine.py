"""PostgreSQL Full Text Search engine with dialect-aware fallback and ranking for LUMO Phase 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from urllib.parse import urlparse

from sqlalchemy import desc, func, literal_column, or_, text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.search.snippet import generate_snippet

logger = get_logger("search.engine")


@dataclass
class SearchResult:
    id: str
    title: str
    url: str
    domain: str
    description: str
    snippet: str
    score: float = 0.0
    published_at: str = ""
    canonical_url: str | None = None
    language: str | None = None
    category: str = "Indexed"
    classic_rank: int | None = None
    semantic_rank: int | None = None
    sources: list[str] = field(default_factory=list)
    hybrid_score: float | None = None


@dataclass
class SearchResultSet:
    query: str
    mode: str
    total: int
    page: int
    per_page: int
    total_pages: int
    results: list[SearchResult] = field(default_factory=list)


class ClassicSearchEngine:
    """Executes PostgreSQL Full Text Search with weights, ranking, filters, and pagination."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 8,
        sort: str = "relevance",
        domain: str | None = None,
        language: str | None = None,
        include_duplicates: bool = False,
    ) -> SearchResultSet:
        """Search indexed documents.

        Args:
            query: User search query.
            page: 1-indexed page number.
            per_page: Results per page.
            sort: 'relevance', 'newest', or 'title'.
            domain: Optional domain filter.
            language: Optional language filter.
            include_duplicates: When False, suppresses duplicate documents.

        Returns:
            SearchResultSet with paginated results and snippets.
        """
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page

        normalized_query = self._normalize_query(query)
        if not normalized_query:
            return SearchResultSet(
                query=query,
                mode="classic",
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                results=[],
            )

        # Detect dialect: PostgreSQL vs SQLite fallback
        dialect_name = self.db.bind.dialect.name if self.db.bind else "sqlite"

        if dialect_name == "postgresql":
            return self._search_postgresql(
                raw_query=query,
                normalized_query=normalized_query,
                page=page,
                per_page=per_page,
                offset=offset,
                sort=sort,
                domain=domain,
                language=language,
                include_duplicates=include_duplicates,
            )
        else:
            return self._search_fallback(
                raw_query=query,
                normalized_query=normalized_query,
                page=page,
                per_page=per_page,
                offset=offset,
                sort=sort,
                domain=domain,
                language=language,
                include_duplicates=include_duplicates,
            )

    def _normalize_query(self, query: str) -> str:
        """Sanitize query string, remove control characters and limit length."""
        if not query:
            return ""
        # Remove non-printable control characters
        cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", query)
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Cap length at 400 characters to prevent resource exhaustion
        return cleaned[:400]

    def _search_postgresql(
        self,
        raw_query: str,
        normalized_query: str,
        page: int,
        per_page: int,
        offset: int,
        sort: str,
        domain: str | None,
        language: str | None,
        include_duplicates: bool,
    ) -> SearchResultSet:
        """Search using PostgreSQL websearch_to_tsquery, tsvector weights, and ts_rank."""
        # 1. Base weights: Title (A=1.0), Description (B=0.4), Main Content (C=0.2)
        tsvector_expr = (
            func.setweight(func.to_tsvector("english", func.coalesce(Document.title, "")), "A").op("||")(
                func.setweight(func.to_tsvector("english", func.coalesce(Document.description, "")), "B")
            ).op("||")(
                func.setweight(func.to_tsvector("english", func.coalesce(Document.main_content, "")), "C")
            )
        )
        tsquery = func.websearch_to_tsquery("english", normalized_query)
        rank_expr = func.ts_rank_cd(tsvector_expr, tsquery)

        query_obj = self.db.query(Document, rank_expr.label("rank_score")).filter(
            tsvector_expr.op("@@")(tsquery)
        )

        # Filters
        if not include_duplicates:
            query_obj = query_obj.filter(Document.is_duplicate.is_(False))
        if domain:
            query_obj = query_obj.filter(Document.domain == domain.lower())
        if language:
            query_obj = query_obj.filter(Document.language.ilike(f"{language}%"))

        total = query_obj.count()

        # Sorting
        if sort == "newest":
            query_obj = query_obj.order_by(Document.created_at.desc())
        elif sort == "title":
            query_obj = query_obj.order_by(Document.title.asc())
        else:  # relevance
            query_obj = query_obj.order_by(desc(literal_column("rank_score")), Document.created_at.desc())

        records = query_obj.offset(offset).limit(per_page).all()

        results: list[SearchResult] = []
        tokens = [t.lower() for t in re.findall(r"\w+", normalized_query) if len(t) > 1]
        for doc, score in records:
            domain_val = doc.domain or (urlparse(doc.url).netloc.lower() if doc.url else "")
            content = doc.main_content or ""
            desc_text = doc.description or ""
            if any(t in content.lower() for t in tokens):
                snippet_source = content
            elif any(t in desc_text.lower() for t in tokens):
                snippet_source = desc_text
            else:
                snippet_source = content or desc_text

            snippet = generate_snippet(snippet_source, normalized_query)
            results.append(
                SearchResult(
                    id=doc.id,
                    title=doc.title or doc.url,
                    url=doc.url,
                    domain=domain_val,
                    description=doc.description or "",
                    snippet=snippet,
                    score=float(score) if score is not None else 0.0,
                    published_at=doc.published_date or doc.created_at.strftime("%Y-%m-%d"),
                    canonical_url=doc.canonical_url,
                    language=doc.language,
                )
            )

        total_pages = max(1, (total + per_page - 1) // per_page)
        return SearchResultSet(
            query=raw_query,
            mode="classic",
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            results=results,
        )

    def _search_fallback(
        self,
        raw_query: str,
        normalized_query: str,
        page: int,
        per_page: int,
        offset: int,
        sort: str,
        domain: str | None,
        language: str | None,
        include_duplicates: bool,
    ) -> SearchResultSet:
        """In-memory and LIKE fallback for SQLite and non-PostgreSQL dialects."""
        tokens = [t.lower() for t in re.findall(r"\w+", normalized_query) if len(t) > 1]
        if not tokens:
            tokens = [normalized_query.lower()]

        # Filter candidate documents matching any token
        token_filters = []
        for t in tokens:
            pattern = f"%{t}%"
            token_filters.append(Document.title.ilike(pattern))
            token_filters.append(Document.description.ilike(pattern))
            token_filters.append(Document.main_content.ilike(pattern))

        query_obj = self.db.query(Document).filter(or_(*token_filters))

        if not include_duplicates:
            query_obj = query_obj.filter(Document.is_duplicate.is_(False))
        if domain:
            query_obj = query_obj.filter(Document.domain == domain.lower())
        if language:
            query_obj = query_obj.filter(Document.language.ilike(f"{language}%"))

        all_candidates = query_obj.all()

        # Score candidates
        scored_candidates: list[tuple[Document, float]] = []
        phrase_lower = normalized_query.lower()

        for doc in all_candidates:
            score = 0.0
            title_lower = (doc.title or "").lower()
            desc_lower = (doc.description or "").lower()
            body_lower = (doc.main_content or "").lower()

            # Exact phrase match bonus
            if phrase_lower in title_lower:
                score += 10.0
            if phrase_lower in desc_lower:
                score += 4.0
            if phrase_lower in body_lower:
                score += 2.0

            # Token overlap scoring
            for t in tokens:
                if t in title_lower:
                    score += 3.0
                if t in desc_lower:
                    score += 1.5
                if t in body_lower:
                    score += 0.5

            scored_candidates.append((doc, score))

        # Filter out 0-score items if any
        scored_candidates = [pair for pair in scored_candidates if pair[1] > 0]
        total = len(scored_candidates)

        # Sort
        if sort == "newest":
            scored_candidates.sort(key=lambda pair: pair[0].created_at or datetime.min, reverse=True)
        elif sort == "title":
            scored_candidates.sort(key=lambda pair: (pair[0].title or "").lower())
        else:  # relevance
            scored_candidates.sort(key=lambda pair: (pair[1], pair[0].created_at or datetime.min), reverse=True)

        paginated = scored_candidates[offset : offset + per_page]

        results: list[SearchResult] = []
        for doc, score in paginated:
            domain_val = doc.domain or (urlparse(doc.url).netloc.lower() if doc.url else "")
            content = doc.main_content or ""
            desc_text = doc.description or ""
            if any(t in content.lower() for t in tokens):
                snippet_source = content
            elif any(t in desc_text.lower() for t in tokens):
                snippet_source = desc_text
            else:
                snippet_source = content or desc_text

            snippet = generate_snippet(snippet_source, normalized_query)
            results.append(
                SearchResult(
                    id=doc.id,
                    title=doc.title or doc.url,
                    url=doc.url,
                    domain=domain_val,
                    description=doc.description or "",
                    snippet=snippet,
                    score=round(score, 2),
                    published_at=doc.published_date or (doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""),
                    canonical_url=doc.canonical_url,
                    language=doc.language,
                )
            )

        total_pages = max(1, (total + per_page - 1) // per_page)
        return SearchResultSet(
            query=raw_query,
            mode="classic",
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            results=results,
        )
