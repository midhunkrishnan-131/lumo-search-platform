"""Tests for LUMO Phase 14: Personal Intelligence & Knowledge Workspace."""

from collections.abc import Generator
import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.api.routes.workspace import get_ai_router
from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.main import create_app


class MockWorkspaceAIResponse:
    def __init__(self, content: str):
        self.content = content


class MockWorkspaceAIRouter:
    def execute(self, prompt: str, requested_provider=None, timeout_seconds=25.0):
        # Include one valid [W1] citation and one hallucinated [W99] citation
        return (
            MockWorkspaceAIResponse("Python is used for FastAPI backends [W1] and quantum [W99]."),
            False,
            "mock-gemini",
        )


@pytest.fixture
def ws_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "workspace_test.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="http://localhost:3000,http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    app = create_app(settings)
    app.dependency_overrides[get_ai_router] = lambda: MockWorkspaceAIRouter()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    dispose_database()


def test_workspace_items_crud_and_deduplication(ws_client: TestClient):
    # Create item
    resp = ws_client.post(
        "/api/v1/workspace/items",
        json={
            "title": "FastAPI Guide",
            "content": "FastAPI is a high-performance Python web framework.",
            "source_type": "bookmark",
            "source_url": "https://fastapi.tiangolo.com",
            "tags": ["Python", "Web"],
        },
    )
    assert resp.status_code == 201
    item = resp.json()
    assert item["title"] == "FastAPI Guide"
    assert item["is_duplicate"] is False
    assert "Python" in item["tags"]
    item_id = item["id"]

    # Duplicate save returns existing item with is_duplicate=True
    dup_resp = ws_client.post(
        "/api/v1/workspace/items",
        json={
            "title": "FastAPI Guide",
            "content": "FastAPI is a high-performance Python web framework.",
            "source_type": "bookmark",
            "source_url": "https://fastapi.tiangolo.com",
            "tags": ["Backend"],
        },
    )
    assert dup_resp.status_code == 201
    dup_data = dup_resp.json()
    assert dup_data["id"] == item_id
    assert dup_data["is_duplicate"] is True
    assert "Backend" in dup_data["tags"]

    # Get marks last_viewed_at
    get_resp = ws_client.get(f"/api/v1/workspace/items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["last_viewed_at"] is not None

    # Update item
    patch_resp = ws_client.patch(f"/api/v1/workspace/items/{item_id}", json={"title": "Updated FastAPI"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated FastAPI"

    # Delete item
    del_resp = ws_client.delete(f"/api/v1/workspace/items/{item_id}")
    assert del_resp.status_code == 204
    assert ws_client.get(f"/api/v1/workspace/items/{item_id}").status_code == 404


def test_collections_notes_and_annotations_lifecycle(ws_client: TestClient):
    # Create collection & rename it
    col_resp = ws_client.post(
        "/api/v1/workspace/collections",
        json={"name": "AI Research", "description": "Papers and notes"},
    )
    assert col_resp.status_code == 201
    col_id = col_resp.json()["id"]

    rename_resp = ws_client.patch(
        f"/api/v1/workspace/collections/{col_id}",
        json={"name": "Machine Learning Research"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "Machine Learning Research"

    # Create item in collection
    item = ws_client.post(
        "/api/v1/workspace/items",
        json={
            "title": "Hybrid Search Note Target",
            "content": "Reciprocal Rank Fusion combines BM25 and Qdrant vector similarity.",
            "collection_id": col_id,
        },
    ).json()

    # Create and edit annotation on item
    ann_resp = ws_client.post(
        f"/api/v1/workspace/items/{item['id']}/annotations",
        json={
            "selected_text": "Reciprocal Rank Fusion",
            "comment": "Key ranking algorithm",
            "start_offset": 0,
            "end_offset": 22,
        },
    )
    assert ann_resp.status_code == 201
    ann_id = ann_resp.json()["id"]

    edit_ann = ws_client.patch(
        f"/api/v1/workspace/annotations/{ann_id}",
        json={"comment": "Updated: RRF fuses lexical and dense ranks"},
    )
    assert edit_ann.status_code == 200
    assert "RRF fuses" in edit_ann.json()["comment"]

    # Create and autosave note linked to item & collection
    note_resp = ws_client.post(
        "/api/v1/workspace/notes",
        json={
            "title": "RRF Summary",
            "content": "# RRF\nInitial draft.",
            "collection_id": col_id,
            "linked_item_id": item["id"],
            "tags": ["Search"],
        },
    )
    assert note_resp.status_code == 201
    note_id = note_resp.json()["id"]

    # Autosave patch
    patch_note = ws_client.patch(
        f"/api/v1/workspace/notes/{note_id}",
        json={"content": "# RRF\nUpdated markdown content."},
    )
    assert patch_note.status_code == 200
    assert "Updated markdown content" in patch_note.json()["content"]

    # Dashboard stats
    dash = ws_client.get("/api/v1/workspace").json()
    assert dash["stats"]["total_items"] == 1
    assert dash["stats"]["total_collections"] == 1
    assert dash["stats"]["total_notes"] == 1
    assert dash["stats"]["total_annotations"] == 1

    # Delete annotation and note
    assert ws_client.delete(f"/api/v1/workspace/annotations/{ann_id}").status_code == 204
    assert ws_client.delete(f"/api/v1/workspace/notes/{note_id}").status_code == 204
    assert ws_client.delete(f"/api/v1/workspace/collections/{col_id}").status_code == 204


def test_document_import_markdown_docx_and_validation(ws_client: TestClient):
    # 1. Markdown import
    md_bytes = b"# Local Knowledge\n\nPython and NetworkX power local intelligence."
    resp_md = ws_client.post(
        "/api/v1/workspace/import",
        files={"file": ("../../secret_notes.md", md_bytes, "text/markdown")},
        data={"tags": "local,python"},
    )
    assert resp_md.status_code == 201
    md_item = resp_md.json()
    assert md_item["title"] == "Local Knowledge"
    assert md_item["file_name"] == "secret_notes.md"  # Path traversal stripped

    # 2. Valid minimal DOCX import
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>DOCX extracted paragraph for LUMO.</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    resp_docx = ws_client.post(
        "/api/v1/workspace/import",
        files={"file": ("report.docx", docx_buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp_docx.status_code == 201
    assert "DOCX extracted paragraph" in resp_docx.json()["content"]

    # 3. Disallowed file extension rejected
    resp_exe = ws_client.post(
        "/api/v1/workspace/import",
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )
    assert resp_exe.status_code == 400

    # 4. SSRF blocked on URL import
    resp_ssrf = ws_client.post(
        "/api/v1/workspace/import-url",
        json={"url": "http://169.254.169.254/latest/meta-data/"},
    )
    assert resp_ssrf.status_code == 400

    # 5. PDF binary import using pypdf
    from pypdf import PdfWriter

    pdf_buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "Sample Empty PDF"})
    writer.write(pdf_buf)
    # Minimal valid PDF with no text raises 400 ("No readable text content")
    resp_empty_pdf = ws_client.post(
        "/api/v1/workspace/import",
        files={"file": ("blank.pdf", pdf_buf.getvalue(), "application/pdf")},
    )
    assert resp_empty_pdf.status_code == 400
    assert "No readable text" in resp_empty_pdf.json()["detail"]


def test_workspace_search_ai_grounding_graph_and_privacy_isolation(ws_client: TestClient):
    # Save personal secret item
    item = ws_client.post(
        "/api/v1/workspace/items",
        json={
            "title": "Private FastAPI Notes",
            "content": "FastAPI uses Python and integrates with Qdrant. PrivateProjectAlpha.",
            "source_type": "note",
            "tags": ["private"],
        },
    ).json()

    # 1. Personal search finds it
    ws_search = ws_client.post(
        "/api/v1/workspace/search",
        json={"query": "PrivateProjectAlpha", "mode": "hybrid"},
    )
    assert ws_search.status_code == 200
    assert ws_search.json()["total"] >= 1

    # 2. Public/General web search MUST NOT expose personal workspace content
    public_search = ws_client.get("/api/v1/search?q=PrivateProjectAlpha&mode=classic")
    assert public_search.status_code == 200
    assert public_search.json()["total"] == 0

    # 3. Personal AI Q&A returns grounded [W1] and strips hallucinated [W99]
    ask_resp = ws_client.post(
        "/api/v1/workspace/ask",
        json={"question": "What does FastAPI use?"},
    )
    assert ask_resp.status_code == 200
    ask_data = ask_resp.json()
    assert ask_data["status"] == "completed"
    assert "[W1]" in ask_data["answer"]
    assert "[W99]" not in ask_data["answer"]
    assert len(ask_data["citations"]) >= 1

    # 4. Insufficient evidence returns gracefully without calling AI
    empty_ask = ws_client.post(
        "/api/v1/workspace/ask",
        json={"question": "ZygoteUnicornNebula12345"},
    )
    assert empty_ask.status_code == 200
    assert empty_ask.json()["status"] == "insufficient_evidence"

    # 5. Knowledge Graph connections
    conn_resp = ws_client.get(f"/api/v1/workspace/items/{item['id']}/connections")
    assert conn_resp.status_code == 200
    entity_names = {e["name"] for e in conn_resp.json()["entities"]}
    assert "FastAPI" in entity_names
    assert "Python" in entity_names
