"""Safe local document & URL importer for LUMO Personal Workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.core.logging import get_logger
from app.guardian.validator import validate_guardian_url
from app.processor.extractor import extract_document_data

logger = get_logger("workspace.importer")

MAX_IMPORT_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_PDF_PAGES = 200
MAX_DOCX_XML_BYTES = 10 * 1024 * 1024  # 10 MB uncompressed XML cap
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".docx"}


@dataclass
class ImportedDocumentPayload:
    title: str
    content: str
    summary: str
    file_name: str | None
    file_type: str
    source_url: str | None
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


def compute_content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _make_summary(text: str, max_len: int = 280) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rsplit(" ", 1)[0] + "..."


class WorkspaceImporter:
    """Validates and extracts text safely from local files and SSRF-screened URLs."""

    def import_bytes(self, filename: str, data: bytes) -> ImportedDocumentPayload:
        if not filename:
            raise ValueError("Filename is required.")

        # Path traversal guard
        safe_name = Path(filename).name.strip()
        if not safe_name or safe_name in (".", ".."):
            raise ValueError("Invalid filename.")

        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        if not data:
            raise ValueError("Uploaded file is empty.")
        if len(data) > MAX_IMPORT_BYTES:
            raise ValueError(f"File exceeds maximum allowed size of {MAX_IMPORT_BYTES // (1024 * 1024)} MB.")

        file_type = ext.lstrip(".")
        title = Path(safe_name).stem
        metadata: dict[str, Any] = {"size_bytes": len(data), "extension": ext}

        if ext in (".txt", ".md", ".markdown"):
            text = data.decode("utf-8", errors="replace").replace("\x00", "").strip()
            # Extract first Markdown heading as title if present
            if ext in (".md", ".markdown"):
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped[2:].strip()[:300] or title
                        break
        elif ext in (".html", ".htm"):
            html_str = data.decode("utf-8", errors="replace")
            extracted = extract_document_data(html_str, f"file:///{safe_name}")
            text = extracted.main_content
            if extracted.title:
                title = extracted.title
            metadata["headings"] = extracted.headings[:20]
        elif ext == ".pdf":
            if not data.lstrip().startswith(b"%PDF-"):
                raise ValueError("Invalid PDF signature: missing %PDF- header.")
            text, pdf_meta = self._extract_pdf(data)
            metadata.update(pdf_meta)
            if pdf_meta.get("pdf_title"):
                title = str(pdf_meta["pdf_title"])[:300]
        elif ext == ".docx":
            if not data.startswith(b"PK\x03\x04"):
                raise ValueError("Invalid DOCX signature: expected ZIP/OOXML container.")
            text, docx_meta = self._extract_docx(data)
            metadata.update(docx_meta)
        else:
            raise ValueError(f"Unsupported extension: {ext}")

        if not text.strip():
            raise ValueError("No readable text content could be extracted from the file.")

        return ImportedDocumentPayload(
            title=title,
            content=text,
            summary=_make_summary(text),
            file_name=safe_name,
            file_type=file_type,
            source_url=None,
            content_hash=compute_content_hash(text),
            metadata=metadata,
        )

    def _extract_pdf(self, data: bytes) -> tuple[str, dict[str, Any]]:
        if not data.startswith(b"%PDF"):
            raise ValueError("File does not have a valid PDF header.")

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        total_pages = len(reader.pages)
        pages_to_read = min(total_pages, MAX_PDF_PAGES)

        parts: list[str] = []
        for idx in range(pages_to_read):
            page_text = reader.pages[idx].extract_text() or ""
            if page_text.strip():
                parts.append(page_text.strip())

        meta: dict[str, Any] = {
            "page_count": total_pages,
            "pages_extracted": pages_to_read,
        }
        if reader.metadata and reader.metadata.title:
            meta["pdf_title"] = str(reader.metadata.title).strip()

        return "\n\n".join(parts), meta

    def _extract_docx(self, data: bytes) -> tuple[str, dict[str, Any]]:
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ValueError("File is not a valid DOCX archive.")

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ValueError("Invalid DOCX structure: missing word/document.xml.")

            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise ValueError("DOCX XML content exceeds safe extraction limit.")

            xml_bytes = zf.read("word/document.xml")

        # Reject XML doctype declarations to prevent entity expansion attacks
        if b"<!DOCTYPE" in xml_bytes[:2048].upper() or b"<!ENTITY" in xml_bytes[:2048].upper():
            raise ValueError("Unsafe XML declarations detected in DOCX.")

        root = ET.fromstring(xml_bytes)
        paragraphs: list[str] = []
        # Extract all text runs grouped by paragraph (<w:p>)
        for elem in root.iter():
            if elem.tag.endswith("}p"):
                texts = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
                line = "".join(texts).strip()
                if line:
                    paragraphs.append(line)

        return "\n\n".join(paragraphs), {"paragraph_count": len(paragraphs)}

    def import_url(self, url: str) -> ImportedDocumentPayload:
        val = validate_guardian_url(url.strip(), resolve_dns=True)
        if not val.is_valid:
            raise ValueError(val.error or "URL blocked by SSRF security policy.")

        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                resp = client.get(val.normalized_url, headers={"User-Agent": "LUMO-Workspace/1.0"})
                if resp.status_code >= 400:
                    raise ValueError(f"Remote URL returned HTTP {resp.status_code}.")
                if len(resp.content) > 2 * 1024 * 1024:
                    raise ValueError("Remote webpage exceeds 2 MB import limit.")
                html_str = resp.text
        except httpx.HTTPError as exc:
            raise ValueError(f"Failed to fetch URL: {type(exc).__name__}") from exc

        extracted = extract_document_data(html_str, val.normalized_url)
        if not extracted.main_content.strip():
            raise ValueError("No readable main content could be extracted from URL.")

        return ImportedDocumentPayload(
            title=extracted.title or val.hostname or val.normalized_url,
            content=extracted.main_content,
            summary=extracted.description or _make_summary(extracted.main_content),
            file_name=None,
            file_type="html",
            source_url=val.normalized_url,
            content_hash=extracted.content_hash,
            metadata={"domain": val.hostname, "headings": extracted.headings[:20]},
        )
