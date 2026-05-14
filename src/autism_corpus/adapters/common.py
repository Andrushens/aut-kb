"""Shared helpers for source adapters.

Each adapter composes these helpers rather than reimplementing common
patterns like "fetch a URL, parse the HTML, build a ParsedDocument".
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from autism_corpus.models import ContentType, ParsedDocument, RawDocument
from autism_corpus.normalize.html import extract_html
from autism_corpus.normalize.pdf import extract_pdf
from autism_corpus.normalize.text import detect_language, normalize_whitespace
from autism_corpus.utils.hashing import canonical_text_hash
from autism_corpus.utils.http import CachedHttpClient

PayloadKind = Literal["html", "pdf"]


def build_parsed_document(
    raw: RawDocument,
    *,
    source_id: str,
    licence: str,
    licence_url: str,
    attribution: str,
    content_type: ContentType,
    medical_disclaimer_required: bool,
    payload_kind: PayloadKind,
    canonical_url: str | None = None,
    published_at: date | None = None,
    title_override: str | None = None,
) -> ParsedDocument:
    """Compose a ParsedDocument from a fetched RawDocument."""
    if payload_kind == "html":
        extraction = extract_html(
            raw.payload.decode("utf-8", errors="replace"), url=raw.url
        )
        title = title_override or extraction.title
        text = normalize_whitespace(extraction.text)
        last_modified_at = extraction.last_modified
    else:
        pdf_extraction = extract_pdf(raw.payload)
        title = title_override or (pdf_extraction.title or raw.source_item_id)
        text = normalize_whitespace(pdf_extraction.text)
        last_modified_at = None

    language = detect_language(text)
    return ParsedDocument(
        source_id=source_id,
        source_item_id=raw.source_item_id,
        canonical_url=canonical_url or raw.url,
        title=title,
        text=text,
        language=language,
        published_at=published_at,
        last_modified_at=last_modified_at,
        licence=licence,
        licence_url=licence_url,
        attribution=attribution,
        content_type=content_type,
        medical_disclaimer_required=medical_disclaimer_required,
        hash=canonical_text_hash(text),
        fetched_at=raw.fetched_at,
    )


def http_get_as_raw_document(
    http_client: CachedHttpClient,
    *,
    source_id: str,
    source_item_id: str,
    url: str,
) -> RawDocument:
    """GET a URL via the shared http client and wrap the response."""
    result = http_client.get(url)
    return RawDocument(
        source_id=source_id,
        source_item_id=source_item_id,
        url=url,
        content_type_header=result.content_type,
        payload=result.payload,
        fetched_at=result.fetched_at,
    )
