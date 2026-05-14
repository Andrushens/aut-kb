"""PDF extraction using pymupdf.

Pages are joined with ``"\n\n"`` after stripping headers/footers that repeat
identically across every page.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from autism_corpus.normalize.text import normalize_whitespace


@dataclass(frozen=True)
class PdfExtraction:
    """Structured result of PDF normalisation."""

    title: str | None
    text: str
    page_count: int


def _extract_pages(doc: pymupdf.Document) -> list[list[str]]:
    """Return per-page list of non-empty stripped lines."""
    pages: list[list[str]] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)  # type: ignore[no-untyped-call]
        raw = page.get_text() or ""
        lines = [line.strip() for line in raw.splitlines()]
        pages.append([line for line in lines if line])
    return pages


def _repeating_lines(pages: list[list[str]]) -> set[str]:
    """Return lines that appear on every page (with at least 2 pages)."""
    if len(pages) < 2:
        return set()
    common: set[str] = set(pages[0])
    for page_lines in pages[1:]:
        common &= set(page_lines)
        if not common:
            break
    return common


def _strip_repeating(pages: list[list[str]]) -> list[str]:
    """Drop lines that repeat on every page; return one joined string per page."""
    repeating = _repeating_lines(pages)
    cleaned_pages: list[str] = []
    for page_lines in pages:
        kept = [line for line in page_lines if line not in repeating]
        cleaned_pages.append("\n".join(kept))
    return cleaned_pages


def _title_from_metadata(doc: pymupdf.Document) -> str | None:
    """Return the PDF /Title metadata field, normalised to ``None`` if empty."""
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    return title or None


def extract_pdf(payload: bytes) -> PdfExtraction:
    """Extract title, text, and page count from a PDF byte payload."""
    doc: pymupdf.Document = pymupdf.open(  # type: ignore[no-untyped-call]
        stream=payload, filetype="pdf"
    )
    try:
        page_count = doc.page_count
        title = _title_from_metadata(doc)
        pages = _extract_pages(doc)
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    page_texts = _strip_repeating(pages)
    joined = "\n\n".join(page_texts)
    # Defensive: pymupdf sometimes emits form-feed page separators; remove any.
    joined = joined.replace("\f", "\n\n")
    text = normalize_whitespace(joined)

    return PdfExtraction(title=title, text=text, page_count=page_count)
