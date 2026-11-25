"""Deterministic tests for LUMO Phase 18: Universal Data Intelligence Engine (no paid API calls)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
import pytest

from app.ai.base import AIProviderResponse
from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.intelligence.security import redact_secrets
from app.main import create_app


@pytest.fixture()
def intel_client(tmp_path: Path):
    db_path = tmp_path / "intel_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_path}",
        local_only_ai=False,
        gemini_api_key="",
        grok_api_key="",
    )
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


def _make_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_docx_bytes(text: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _make_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Region", "Revenue", "Units"])
    ws.append(["North", 1200, 10])
    ws.append(["South", 800, 8])
    ws.append(["North", 1200, 10])  # intentional duplicate row
    ws.append(["West", None, 5])    # intentional missing value
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Metric", "Value"])
    ws2.append(["Total", 3200])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_png_bytes() -> bytes:
    # Minimal valid 1x1 PNG signature + IHDR + IEND
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_security_validation_and_key_redaction(intel_client: TestClient):
    # Spoofed PDF header rejected
    bad_pdf = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")},
    )
    assert bad_pdf.status_code == 400
    assert "PDF signature" in bad_pdf.json()["detail"]

    # Spoofed PNG rejected
    bad_png = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("fake.png", b"not-png", "image/png")},
    )
    assert bad_png.status_code == 400

    # Unsupported extension rejected
    bad_exe = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )
    assert bad_exe.status_code == 400

    # Key redaction never leaks secrets
    leaked = "Error calling https://api.example.com?key=AQ.SecretKey12345678901234567890 with grok_abc12345678901234567890"
    redacted = redact_secrets(leaked)
    assert "AQ.SecretKey" not in redacted
    assert "grok_abc" not in redacted
    assert "[REDACTED]" in redacted


def test_multi_format_ingestion_graph_search_and_deletion(intel_client: TestClient):
    # 1. Markdown invoice -> deterministic classification = invoice
    md_resp = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("invoice_q4.md", b"# Invoice #1042\nBill To: Acme Corp\nSubtotal: $500\nAmount Due: $500\nDate: 2026-11-01", "text/markdown")},
    )
    assert md_resp.status_code == 201
    md_job = md_resp.json()
    assert md_job["status"] == "completed"
    assert md_job["content_category"] == "invoice"

    # 2. DOCX document
    docx_resp = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("notes.docx", _make_docx_bytes("FastAPI and PostgreSQL architecture notes for LUMO."), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert docx_resp.status_code == 201
    assert docx_resp.json()["format_type"] == "docx"

    # 3. JSONL structured dataset
    jsonl_data = b'{"city": "Seattle", "temp": 55}\n{"city": "Austin", "temp": 78}\n'
    jsonl_resp = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("weather.jsonl", jsonl_data, "application/json")},
    )
    assert jsonl_resp.status_code == 201
    assert jsonl_resp.json()["dataset_id"] is not None

    # 4. PNG image metadata
    png_resp = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("diagram.png", _make_png_bytes(), "image/png")},
    )
    assert png_resp.status_code == 201
    assert png_resp.json()["content_category"] == "image"

    # 5. Search integration (Workspace Search indexes ingested content)
    ws_search = intel_client.post("/api/v1/workspace/search", json={"query": "Acme", "mode": "keyword"})
    assert ws_search.status_code == 200
    assert ws_search.json()["total"] >= 1

    # 6. Knowledge Graph integration
    graph_stats = intel_client.get("/api/v1/graph/stats").json()
    assert graph_stats["total_entities"] >= 1

    # 7. Deletion synchronization removes job, dataset, and workspace item
    ds_id = jsonl_resp.json()["dataset_id"]
    del_resp = intel_client.delete(f"/api/v1/intelligence/imports/{jsonl_resp.json()['id']}")
    assert del_resp.status_code == 200
    assert intel_client.get(f"/api/v1/intelligence/datasets/{ds_id}").status_code == 404


def test_spreadsheet_profiling_analyst_charts_and_cross_analysis(intel_client: TestClient):
    # Upload multi-sheet XLSX
    xlsx_resp = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("sales.xlsx", _make_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert xlsx_resp.status_code == 201
    ds_id = xlsx_resp.json()["dataset_id"]
    assert ds_id

    profile = intel_client.get(f"/api/v1/intelligence/datasets/{ds_id}/profile").json()
    assert profile["row_count"] == 4
    assert profile["column_count"] == 3
    assert profile["sheet_count"] == 2
    assert profile["profile_json"]["duplicate_rows"] == 1
    assert profile["profile_json"]["total_missing_cells"] == 1

    # Switch sheet
    sheet2 = intel_client.get(f"/api/v1/intelligence/datasets/{ds_id}/profile?sheet=Summary").json()
    assert sheet2["active_sheet"] == "Summary"
    assert sheet2["row_count"] == 1

    # Switch back to Sales for chart & analyst
    intel_client.get(f"/api/v1/intelligence/datasets/{ds_id}/profile?sheet=Sales")

    # Deterministic AI Data Analyst with mocked AI explanation
    mock_ai = AIProviderResponse(content="North leads with 2400 total Revenue; 1 missing cell in Revenue.", provider="gemini", model="gemini-1.5-flash")
    with patch("app.ai.router.AIProviderRouter.execute", return_value=(mock_ai, False, "gemini")):
        analyst_resp = intel_client.post(
            f"/api/v1/intelligence/datasets/{ds_id}/analyze",
            json={"question": "Which category has highest Revenue and what are the missing values?"},
        )
    assert analyst_resp.status_code == 200
    rep = analyst_resp.json()
    assert rep["provider"] == "gemini"
    assert rep["result_json"]["computed_metrics"]["total_missing_cells"] == 1

    # Visualization endpoints (bar, histogram, scatter)
    bar = intel_client.post(
        f"/api/v1/intelligence/datasets/{ds_id}/visualize",
        json={"chart_type": "bar", "x_column": "Region", "y_column": "Revenue"},
    )
    assert bar.status_code == 200
    assert "North" in bar.json()["labels"]

    scatter = intel_client.post(
        f"/api/v1/intelligence/datasets/{ds_id}/visualize",
        json={"chart_type": "scatter", "x_column": "Units", "y_column": "Revenue"},
    )
    assert scatter.status_code == 200
    assert len(scatter.json()["points"]) == 3

    # Document analysis & cross-document comparison
    d1 = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("doc1.txt", b"Python and FastAPI power LUMO backend services as of 2026-10-01.", "text/plain")},
    ).json()["workspace_item_id"]
    d2 = intel_client.post(
        "/api/v1/intelligence/import",
        files={"file": ("doc2.txt", b"FastAPI integrates with Qdrant and PostgreSQL in LUMO.", "text/plain")},
    ).json()["workspace_item_id"]

    with patch("app.ai.router.AIProviderRouter.execute", return_value=(mock_ai, False, "gemini")):
        doc_an = intel_client.post(
            f"/api/v1/intelligence/documents/{d1}/analyze",
            json={"mode": "summarize"},
        )
        assert doc_an.status_code == 200

        cross = intel_client.post(
            "/api/v1/intelligence/cross-analysis",
            json={"source_ids": [d1, d2], "question": "Compare the technologies mentioned."},
        )
        assert cross.status_code == 200
        assert len(cross.json()["source_ids"]) == 2
