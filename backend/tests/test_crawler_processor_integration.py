"""Tests for Crawler Engine and Document Processor pipeline integration."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from app.crawler.engine import CrawlerEngine
from app.crawler.fetcher import FetchResult
from app.database.connection import (
    create_tables,
    dispose_database,
    get_session_factory,
    init_database,
)
from app.models.crawler import CrawlSession, CrawlUrl
from app.models.document import Document


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "integration_test.db"
    init_database(f"sqlite:///{db_file}")
    create_tables()

    yield get_session_factory()

    dispose_database()


def test_crawler_automatically_processes_html_into_documents(test_db):
    async def _run():
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Distributed Systems Architecture</title>
            <meta name="description" content="Consensus protocols and partition tolerance.">
        </head>
        <body>
            <nav><a href="/">Home</a></nav>
            <article>
                <h1>Distributed Systems Architecture</h1>
                <p>Raft and Paxos ensure consistency across replicated state machines.</p>
            </article>
        </body>
        </html>
        """

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch.return_value = FetchResult(
            url="https://93.184.216.34/article",
            status_code=200,
            content_type="text/html; charset=utf-8",
            content_length=len(sample_html),
            text=sample_html,
            success=True,
        )
        mock_fetcher.close = AsyncMock()

        mock_robots = AsyncMock()
        mock_robots.can_fetch.return_value = (True, 0.0)

        # 1. Create a crawl session in DB with 1 seed
        session_id = "test-session-int-1"
        with test_db() as db:
            session = CrawlSession(
                id=session_id,
                name="Integration Test",
                max_depth=1,
                max_pages=2,
                crawl_delay=0.0,
            )
            url_rec = CrawlUrl(
                session_id=session_id,
                url="https://93.184.216.34/article",
                normalized_url="https://93.184.216.34/article",
                depth=0,
                is_seed=True,
                status="queued",
            )
            db.add(session)
            db.add(url_rec)
            db.commit()

        # 2. Run engine
        engine = CrawlerEngine(
            robots_manager=mock_robots,
            fetcher_factory=lambda **kwargs: mock_fetcher,
        )

        await engine.start_session(
            session_id=session_id,
            session_factory=test_db,
        )

        # Wait for session task to finish
        task = engine._active_tasks.get(session_id)
        if task:
            await task

        # 3. Verify Documents were created and linked to the session & url
        with test_db() as db:
            sess = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
            assert sess.status == "completed"
            assert sess.pages_crawled == 2

            docs = db.query(Document).filter(Document.session_id == session_id).order_by(Document.created_at.asc()).all()
            assert len(docs) == 2

            # First crawled page is primary document
            primary_doc = docs[0]
            assert primary_doc.title == "Distributed Systems Architecture"
            assert primary_doc.description == "Consensus protocols and partition tolerance."
            assert "Raft and Paxos" in primary_doc.main_content
            assert primary_doc.is_duplicate is False
            assert primary_doc.primary_document_id is None
            assert primary_doc.extraction_status == "completed"

            # Second crawled page had identical content and was marked duplicate
            dup_doc = docs[1]
            assert dup_doc.is_duplicate is True
            assert dup_doc.primary_document_id == primary_doc.id

    asyncio.run(_run())
