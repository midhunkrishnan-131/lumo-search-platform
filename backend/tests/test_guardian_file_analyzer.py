"""Unit tests for Guardian File Security Analyzer and static file inspection."""

import io
from pathlib import Path
import struct
import zipfile

import pytest

from app.guardian.file_analyzer import FileSecurityAnalyzer, compute_shannon_entropy


def test_file_analyzer_hashes_and_signature_pdf():
    analyzer = FileSecurityAnalyzer()
    pdf_content = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"

    hashes, detected_format, detected_mime, findings, static_features, file_size = (
        analyzer.analyze_file_stream(io.BytesIO(pdf_content), "sample.pdf")
    )

    assert detected_format == "PDF Document"
    assert detected_mime == "application/pdf"
    assert len(hashes["sha256"]) == 64
    assert len(hashes["sha1"]) == 40
    assert len(hashes["md5"]) == 32
    assert file_size == len(pdf_content)


def test_file_analyzer_detects_extension_mismatch_disguised_exe():
    analyzer = FileSecurityAnalyzer()
    # Executable header MZ disguised with .pdf extension
    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100

    hashes, detected_format, detected_mime, findings, _, _ = (
        analyzer.analyze_file_stream(io.BytesIO(fake_pdf), "invoice_december.pdf")
    )

    assert detected_format == "Windows PE Executable / DLL"
    names = {f.name for f in findings}
    assert "File Extension and Magic Signature Mismatch" in names
    # Critical severity for PE disguised as document
    mismatch_finding = next(f for f in findings if f.name == "File Extension and Magic Signature Mismatch")
    assert mismatch_finding.severity == "critical"


def test_file_analyzer_detects_pdf_active_triggers():
    analyzer = FileSecurityAnalyzer()
    pdf_with_js = b"%PDF-1.4\n<< /JavaScript (app.alert('pwn')) /Launch (cmd.exe) >>\n"

    _, _, _, findings, static_features, _ = (
        analyzer.analyze_file_stream(io.BytesIO(pdf_with_js), "form.pdf")
    )

    names = {f.name for f in findings}
    assert "Embedded JavaScript in PDF" in names
    assert "Automatic Application Launch Action in PDF" in names
    assert "/Launch" in static_features.get("pdf_triggers", [])


def test_file_analyzer_detects_zip_slip_path_traversal():
    analyzer = FileSecurityAnalyzer()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../etc/cron.d/malicious", b"exploit payload")

    zip_bytes = zip_buffer.getvalue()
    _, _, _, findings, _, _ = analyzer.analyze_file_stream(io.BytesIO(zip_bytes), "archive.zip")

    names = {f.name for f in findings}
    assert "Archive Path Traversal Attempt (Zip Slip)" in names


def test_file_analyzer_detects_zip_executable_binary():
    analyzer = FileSecurityAnalyzer()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("payload.exe", b"binary content")

    zip_bytes = zip_buffer.getvalue()
    _, _, _, findings, _, _ = analyzer.analyze_file_stream(io.BytesIO(zip_bytes), "bundle.zip")

    names = {f.name for f in findings}
    assert "Executable Binary Found Inside Archive" in names


def test_file_analyzer_detects_office_vba_macros():
    analyzer = FileSecurityAnalyzer()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("word/vbaProject.bin", b"VBA macro binary code")

    zip_bytes = zip_buffer.getvalue()
    _, _, _, findings, static_features, _ = analyzer.analyze_file_stream(io.BytesIO(zip_bytes), "invoice.docx")

    names = {f.name for f in findings}
    assert "Embedded VBA Macros in Office Document" in names
    assert static_features.get("has_vba_macros") is True


def test_file_analyzer_detects_dangerous_script_primitives():
    analyzer = FileSecurityAnalyzer()
    script = (
        "# Setup script\n"
        "powershell.exe -enc JABzAD0ATgBlAHcALQBPAGIAagBlAGMAdAA=\n"
        "Invoke-Expression $s\n"
    ).encode("utf-8")

    _, _, _, findings, _, _ = analyzer.analyze_file_stream(io.BytesIO(script), "install.ps1")

    names = {f.name for f in findings}
    assert "Encoded PowerShell Execution" in names
    assert "PowerShell Dynamic Code Execution (Invoke-Expression)" in names


def test_file_analyzer_enforces_upload_size_limit():
    analyzer = FileSecurityAnalyzer()
    huge_data = io.BytesIO(b"0" * (1024 * 1024))

    # Test limit of 512KB
    with pytest.raises(ValueError, match="exceeds maximum allowed upload size"):
        with analyzer.create_safe_temp_file(huge_data, max_size=512 * 1024):
            pass


def test_shannon_entropy_calculation():
    # Uniform bytes has low entropy
    low_entropy = compute_shannon_entropy(b"\x00" * 1000)
    assert low_entropy == 0.0

    # Diverse random-like bytes has high entropy (~8.0)
    diverse = bytes([i % 256 for i in range(1024)])
    high_entropy = compute_shannon_entropy(diverse)
    assert high_entropy >= 7.8
