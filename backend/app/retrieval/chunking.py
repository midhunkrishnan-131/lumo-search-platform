"""Format-aware document chunking engine for LUMO Phase 29."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass
class StructuredChunk:
    document_id: str
    title: str
    source: str
    chunk_index: int
    text: str
    approx_tokens: int
    content_type: str
    section: str | None = None
    page_number: int | None = None


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _split_with_overlap(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    clean = (text or "").strip()
    if not clean:
        return []
    # Invalid sizes used to emit empty slices or skip the tail of a block.
    chunk_size = max(1, chunk_size)
    chunk_overlap = min(max(0, chunk_overlap), chunk_size - 1)
    if len(clean) <= chunk_size:
        return [clean]
    paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    step = max(1, chunk_size - chunk_overlap)

    def _windows(unit: str) -> list[str]:
        return [unit[i : i + chunk_size] for i in range(0, len(unit), step)]

    chunks: list[str] = []
    cur = ""
    for unit in paragraphs:
        if not unit:
            continue
        separator = 2 if cur else 0
        if len(cur) + len(unit) + separator <= chunk_size:
            cur = f"{cur}\n\n{unit}".strip() if cur else unit
            continue
        if cur:
            chunks.append(cur)
            tail = cur[-chunk_overlap:] if chunk_overlap > 0 else ""
            if tail and len(tail) + len(unit) + 1 <= chunk_size:
                cur = f"{tail} {unit}".strip()
                continue
            cur = ""
        if len(unit) <= chunk_size:
            cur = unit
        else:
            # Keep every window. Taking only unit[:chunk_size] dropped the rest.
            chunks.extend(_windows(unit))
    if cur:
        chunks.append(cur)
    return chunks


def chunk_content(
    text: str,
    document_id: str,
    title: str = "",
    source: str = "",
    content_type: str = "text",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[StructuredChunk]:
    """Chunk text using format-appropriate boundaries while preserving section/page metadata."""
    raw = (text or "").strip()
    if not raw:
        return []
    ctype = (content_type or "text").lower().strip()
    out: list[StructuredChunk] = []
    idx = 0

    if ctype == "pdf" and ("\f" in raw or "[Page " in raw):
        pages = raw.split("\f") if "\f" in raw else re.split(r"\[Page\s+\d+\]", raw)
        for p_num, page_txt in enumerate(pages, start=1):
            for piece in _split_with_overlap(page_txt, chunk_size, chunk_overlap):
                out.append(StructuredChunk(
                    document_id=document_id,
                    title=title,
                    source=source,
                    chunk_index=idx,
                    text=piece,
                    approx_tokens=_estimate_tokens(piece),
                    content_type=ctype,
                    page_number=p_num,
                ))
                idx += 1
        return out

    if ctype in ("markdown", "md"):
        sections = re.split(r"(?m)^(#{1,3}\s+.+)$", raw)
        cur_sec: str | None = None
        buf = ""
        for part in sections:
            s = part.strip()
            if not s:
                continue
            if re.match(r"^#{1,3}\s+", s):
                if buf:
                    for piece in _split_with_overlap(buf, chunk_size, chunk_overlap):
                        out.append(StructuredChunk(
                            document_id=document_id, title=title, source=source,
                            chunk_index=idx, text=piece, approx_tokens=_estimate_tokens(piece),
                            content_type=ctype, section=cur_sec,
                        ))
                        idx += 1
                    buf = ""
                cur_sec = s.lstrip("#").strip()
            else:
                buf = f"{buf}\n\n{s}".strip() if buf else s
        if buf:
            for piece in _split_with_overlap(buf, chunk_size, chunk_overlap):
                out.append(StructuredChunk(
                    document_id=document_id, title=title, source=source,
                    chunk_index=idx, text=piece, approx_tokens=_estimate_tokens(piece),
                    content_type=ctype, section=cur_sec,
                ))
                idx += 1
        return out

    for piece in _split_with_overlap(raw, chunk_size, chunk_overlap):
        out.append(StructuredChunk(
            document_id=document_id,
            title=title,
            source=source,
            chunk_index=idx,
            text=piece,
            approx_tokens=_estimate_tokens(piece),
            content_type=ctype,
        ))
        idx += 1
    return out
