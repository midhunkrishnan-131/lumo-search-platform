"""Tests for Classic Search Engine, ranking, filters, and snippet generation."""

import pytest
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.models.document import Document
from app.search.engine import ClassicSearchEngine
from app.search.snippet import generate_snippet


@pytest.fixture
def search_db(tmp_path):
    db_file = tmp_path / "search_test.db"
    init_database(f"sqlite:///{db_file}")
    create_tables()

    session_factory = get_session_factory()
    with session_factory() as session:
        # Seed documents for search
        doc1 = Document(
            id="doc-1",
            url="https://docs.python.org/3/tutorial/",
            domain="docs.python.org",
            title="The Python Tutorial",
            description="Python is an easy to learn, powerful programming language.",
            main_content="Python has efficient high-level data structures and a simple but effective approach to object-oriented programming.",
            language="en",
            is_duplicate=False,
            content_hash="hash1",
        )
        doc2 = Document(
            id="doc-2",
            url="https://fastapi.tiangolo.com/tutorial/",
            domain="fastapi.tiangolo.com",
            title="FastAPI Tutorial - User Guide",
            description="FastAPI framework, high performance, easy to learn, fast to code, ready for production.",
            main_content="FastAPI is a modern, fast web framework for building APIs with Python based on standard Python type hints.",
            language="en",
            is_duplicate=False,
            content_hash="hash2",
        )
        doc3 = Document(
            id="doc-3",
            url="https://docs.python.org/3/library/sqlite3.html",
            domain="docs.python.org",
            title="sqlite3 — DB-API 2.0 interface for SQLite databases",
            description="SQLite is a C library that provides a lightweight disk-based database.",
            main_content="The sqlite3 module provides a SQL interface compliant with the DB-API 2.0 specification.",
            language="en",
            is_duplicate=False,
            content_hash="hash3",
        )
        doc_dup = Document(
            id="doc-4-dup",
            url="https://mirror.python.org/tutorial/",
            domain="mirror.python.org",
            title="The Python Tutorial (Mirror)",
            description="Python is an easy to learn, powerful programming language.",
            main_content="Python has efficient high-level data structures and a simple but effective approach to object-oriented programming.",
            language="en",
            is_duplicate=True,
            content_hash="hash1",
        )
        session.add_all([doc1, doc2, doc3, doc_dup])
        session.commit()

        yield session

    dispose_database()


def test_snippet_generation():
    text = "Modern search engines index documents to provide sub-second retrieval across large corpora."
    snippet = generate_snippet(text, "search engines", max_chars=120)
    assert "<b>search</b> <b>engines</b>" in snippet
    assert "..." not in snippet  # Fits within 120 chars

    # Truncation when exceeding max_chars
    long_snippet = generate_snippet(text, "search engines", max_chars=40)
    assert "..." in long_snippet


def test_snippet_highlighting_is_escaped():
    evil_text = "<script>alert('xss')</script> Python is a high-level programming language."
    snippet = generate_snippet(evil_text, "Python", max_chars=100)
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet
    assert "<b>Python</b>" in snippet


def test_empty_query_returns_zero_results(search_db):
    engine = ClassicSearchEngine(search_db)
    res = engine.search("")
    assert res.total == 0
    assert len(res.results) == 0


def test_search_by_title_ranks_higher_than_body(search_db):
    engine = ClassicSearchEngine(search_db)
    # Both doc1 and doc2 mention Python, but doc1 has "Python" in the title
    res = engine.search("Python")
    assert res.total >= 2
    assert res.results[0].id == "doc-1"  # doc1 title is "The Python Tutorial"


def test_search_filters_by_domain(search_db):
    engine = ClassicSearchEngine(search_db)
    # Search "Python" only within fastapi.tiangolo.com
    res = engine.search("Python", domain="fastapi.tiangolo.com")
    assert res.total == 1
    assert res.results[0].id == "doc-2"
    assert res.results[0].domain == "fastapi.tiangolo.com"


def test_search_excludes_duplicates_by_default(search_db):
    engine = ClassicSearchEngine(search_db)
    res = engine.search("Python", include_duplicates=False)
    doc_ids = [r.id for r in res.results]
    assert "doc-4-dup" not in doc_ids


def test_search_pagination(search_db):
    engine = ClassicSearchEngine(search_db)
    # Page 1, per_page 1
    res1 = engine.search("Python", page=1, per_page=1)
    assert res1.total >= 2
    assert len(res1.results) == 1
    assert res1.page == 1
    assert res1.total_pages >= 2

    # Page 2, per_page 1
    res2 = engine.search("Python", page=2, per_page=1)
    assert len(res2.results) == 1
    assert res2.page == 2
    assert res2.results[0].id != res1.results[0].id
