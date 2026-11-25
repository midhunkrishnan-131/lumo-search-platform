"""Tests for document deduplication and content hashing."""

import pytest
from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database, get_session_factory
from app.models.document import Document
from app.processor.pipeline import process_document


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "dedup_test.db"
    db_url = f"sqlite:///{db_file}"
    init_database(db_url)
    create_tables()

    session_factory = get_session_factory()
    with session_factory() as session:
        yield session

    dispose_database()


def test_identical_content_detection(db_session):
    # Two HTML pages with different outer navigation/wrapper but identical article content
    html_1 = """
    <html>
    <head><title>Original Post</title></head>
    <body>
        <nav><a href="/1">Nav 1</a></nav>
        <article>
            <h1>Standard Title</h1>
            <p>This is the identical body text describing an algorithm in detail.</p>
        </article>
        <footer>Footer 1</footer>
    </body>
    </html>
    """

    html_2 = """
    <html>
    <head><title>Syndicated Copy</title></head>
    <body>
        <div class="cookie-banner">Accept cookies</div>
        <aside>Ad widget</aside>
        <article>
            <h1>Standard Title</h1>
            <p>This is the identical body text describing an algorithm in detail.</p>
        </article>
        <footer>Different Footer 2026</footer>
    </body>
    </html>
    """

    # Process first document
    doc1 = process_document(
        html=html_1,
        url="https://source.example.com/article",
        db=db_session,
    )
    db_session.commit()

    assert not doc1.is_duplicate
    assert doc1.primary_document_id is None
    assert doc1.content_hash != ""

    # Process second document
    doc2 = process_document(
        html=html_2,
        url="https://mirror.example.com/repost",
        db=db_session,
    )
    db_session.commit()

    assert doc2.is_duplicate is True
    assert doc2.primary_document_id == doc1.id
    assert doc2.content_hash == doc1.content_hash
