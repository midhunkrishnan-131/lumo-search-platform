"""Document chunking service preserving paragraph boundaries and metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import uuid

from app.models.document import Document


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    chunk_position: int
    chunk_text: str
    title: str
    url: str
    domain: str
    heading: str | None
    content_hash: str
    indexed_timestamp: datetime


def chunk_document(
    doc: Document,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[DocumentChunk]:
    """Split a processed document into meaningful text chunks with overlap.

    Args:
        doc: Processed Document model instance.
        chunk_size: Target character count per chunk.
        chunk_overlap: Overlap characters between adjacent chunks.

    Returns:
        List of DocumentChunk instances.
    """
    raw_text = (doc.main_content or "").strip()
    if not raw_text:
        # Fallback to description or title if body is empty
        fallback_text = (doc.description or doc.title or "").strip()
        if not fallback_text:
            return []
        raw_text = fallback_text

    # Split paragraphs by double newline (standard LUMO normalizer convention)
    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [raw_text]

    # Further break down excessively large paragraphs by sentences
    units: list[str] = []
    for p in paragraphs:
        if len(p) <= chunk_size:
            units.append(p)
        else:
            sentences = re.split(r"(?<=[.!?])\s+", p)
            current_unit = ""
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if len(current_unit) + len(s) + 1 <= chunk_size:
                    current_unit = f"{current_unit} {s}".strip() if current_unit else s
                else:
                    if current_unit:
                        units.append(current_unit)
                    # If a single sentence exceeds chunk_size, cut it by words
                    if len(s) > chunk_size:
                        words = s.split()
                        sub_chunk = ""
                        for w in words:
                            if len(sub_chunk) + len(w) + 1 <= chunk_size:
                                sub_chunk = f"{sub_chunk} {w}".strip() if sub_chunk else w
                            else:
                                if sub_chunk:
                                    units.append(sub_chunk)
                                sub_chunk = w
                        if sub_chunk:
                            units.append(sub_chunk)
                        current_unit = ""
                    else:
                        current_unit = s
            if current_unit:
                units.append(current_unit)

    # Group units into chunks respecting chunk_size and chunk_overlap
    chunks: list[str] = []
    current_chunk = ""

    for u in units:
        if not current_chunk:
            current_chunk = u
        elif len(current_chunk) + len(u) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{u}"
        else:
            chunks.append(current_chunk)
            # Create overlap from end of previous chunk
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                overlap_text = current_chunk[-chunk_overlap:]
                # Align to word boundary
                space_idx = overlap_text.find(" ")
                if space_idx != -1:
                    overlap_text = overlap_text[space_idx + 1 :]
                current_chunk = f"{overlap_text}\n\n{u}"
            else:
                current_chunk = u

    if current_chunk:
        chunks.append(current_chunk)

    now = datetime.now(timezone.utc)
    title_str = doc.title or doc.url or "Untitled"
    domain_str = doc.domain or ""

    result: list[DocumentChunk] = []
    for pos, text in enumerate(chunks):
        cleaned_chunk = text.strip()
        if len(cleaned_chunk) < 15:  # Skip trivial fragments
            continue

        # Deterministic UUID generation from document_id and position
        chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.id}_chunk_{pos}"))
        chunk_hash = hashlib.sha256(cleaned_chunk.encode("utf-8")).hexdigest()

        result.append(
            DocumentChunk(
                chunk_id=chunk_uuid,
                document_id=doc.id,
                chunk_position=pos,
                chunk_text=cleaned_chunk,
                title=title_str,
                url=doc.url,
                domain=domain_str,
                heading=None,
                content_hash=chunk_hash,
                indexed_timestamp=now,
            )
        )

    return result
