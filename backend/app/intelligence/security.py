"""Security, file signature validation, path traversal protection, and key redaction for Phase 18."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import zipfile

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_JSON_BYTES = 15 * 1024 * 1024    # 15 MB
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB zip-bomb cap

SUPPORTED_DOCUMENT_EXTS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"}
SUPPORTED_SPREADSHEET_EXTS = {".csv", ".xlsx"}
SUPPORTED_STRUCTURED_EXTS = {".json", ".jsonl"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

ALL_SUPPORTED_EXTS = (
    SUPPORTED_DOCUMENT_EXTS
    | SUPPORTED_SPREADSHEET_EXTS
    | SUPPORTED_STRUCTURED_EXTS
    | SUPPORTED_IMAGE_EXTS
)

_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z_-]{20,})"),
    re.compile(r"(AQ\.[0-9A-Za-z_-]{20,})"),
    re.compile(r"(grok_[0-9A-Za-z_]{20,})"),
    re.compile(r"(xai-[0-9A-Za-z_-]{20,})"),
    re.compile(r"(lumo_pk_[0-9A-Za-z_-]{16,})"),
    re.compile(r"([?&]key=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[0-9A-Za-z._-]+", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Redact API keys or authorization tokens from log/error strings."""
    if not text:
        return text
    cleaned = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 1 and ("key=" in pat.pattern or "Bearer" in pat.pattern):
            cleaned = pat.sub(r"\1[REDACTED]", cleaned)
        else:
            cleaned = pat.sub("[REDACTED]", cleaned)
    return cleaned


def sanitize_filename(filename: str) -> tuple[str, str]:
    """Validate filename against path traversal and return (safe_name, lowercase_ext)."""
    if not filename or not filename.strip():
        raise ValueError("Filename is required.")
    raw = filename.replace("\\", "/")
    safe_name = Path(raw).name.strip()
    if not safe_name or safe_name in (".", "..") or "\x00" in safe_name:
        raise ValueError("Invalid filename.")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALL_SUPPORTED_EXTS:
        raise ValueError(
            f"Unsupported file format '{ext or 'none'}'. Supported: {', '.join(sorted(ALL_SUPPORTED_EXTS))}"
        )
    return safe_name, ext


def validate_file_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Validate upload size, extension, and magic-byte file signature without executing content."""
    safe_name, ext = sanitize_filename(filename)
    if not data:
        raise ValueError("Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds maximum size limit ({MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    # Magic-byte & structural validation
    if ext == ".pdf":
        if not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature: missing %PDF- header.")
    elif ext in (".docx", ".xlsx"):
        if not data.startswith(b"PK\x03\x04"):
            raise ValueError(f"Invalid {ext.upper()} signature: expected ZIP/OOXML container.")
        # Guard against zip bombs
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise ValueError("Archive uncompressed size exceeds safety limit.")
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Corrupted {ext.upper()} archive.") from exc
    elif ext == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid PNG file signature.")
    elif ext in (".jpg", ".jpeg"):
        if not data.startswith(b"\xff\xd8\xff"):
            raise ValueError("Invalid JPEG file signature.")
    elif ext == ".webp":
        if not (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
            raise ValueError("Invalid WebP file signature.")
    elif ext in (".json", ".jsonl") and len(data) > MAX_JSON_BYTES:
        raise ValueError(f"Structured JSON exceeds maximum size limit ({MAX_JSON_BYTES // (1024 * 1024)} MB).")

    return safe_name, ext


def dataset_storage_dir() -> Path:
    """Return bounded local storage directory for ingested datasets."""
    base = Path(__file__).resolve().parents[2] / "data" / "intelligence_datasets"
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_dataset_blob(dataset_id: str, ext: str, data: bytes) -> Path:
    """Persist validated dataset bytes safely under dataset_storage_dir using UUID filename."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", dataset_id)
    target = (dataset_storage_dir() / f"{safe_id}{ext}").resolve()
    if dataset_storage_dir().resolve() not in target.parents:
        raise ValueError("Invalid dataset storage path.")
    target.write_bytes(data)
    return target


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
