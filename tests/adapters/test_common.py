from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.models import RawDocument
from autism_corpus.utils.http import CachedHttpClient

_HTML = """<!doctype html>
<html>
<head><title>Signs of autism</title>
<meta name="last-modified" content="2024-01-10">
</head>
<body>
<nav>menu</nav>
<main>
<h1>Signs of autism</h1>
<p>This is a paragraph describing signs of autism in young children.
It contains enough words to be useful for language detection.</p>
<h2>In toddlers</h2>
<p>Toddlers may exhibit certain behaviours that parents notice early.</p>
</main>
<footer>copyright</footer>
</body>
</html>
"""


class TestBuildParsedDocumentHtml:
    def test_round_trip_from_raw_html(self) -> None:
        raw = RawDocument(
            source_id="nhs-autism",
            source_item_id="signs",
            url="https://example.test/signs",
            content_type_header="text/html",
            payload=_HTML.encode("utf-8"),
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )
        doc = build_parsed_document(
            raw,
            source_id="nhs-autism",
            licence="OGL-UK-3.0",
            licence_url="https://example.test/ogl",
            attribution="From NHS",
            content_type="patient-info",
            medical_disclaimer_required=False,
            payload_kind="html",
        )
        assert doc.source_id == "nhs-autism"
        assert doc.canonical_url == "https://example.test/signs"
        assert doc.licence == "OGL-UK-3.0"
        assert doc.attribution == "From NHS"
        assert doc.title == "Signs of autism"
        assert doc.language == "en"
        assert "Signs of autism" in doc.text
        assert doc.last_modified_at is not None
        assert doc.last_modified_at.isoformat() == "2024-01-10"
        assert len(doc.hash) == 64

    def test_canonical_url_override(self) -> None:
        raw = RawDocument(
            source_id="nhs-autism",
            source_item_id="signs",
            url="https://example.test/internal/signs",
            content_type_header="text/html",
            payload=_HTML.encode("utf-8"),
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )
        doc = build_parsed_document(
            raw,
            source_id="nhs-autism",
            licence="OGL-UK-3.0",
            licence_url="x",
            attribution="x",
            content_type="patient-info",
            medical_disclaimer_required=False,
            payload_kind="html",
            canonical_url="https://example.test/public/signs",
        )
        assert doc.canonical_url == "https://example.test/public/signs"

    def test_title_override(self) -> None:
        raw = RawDocument(
            source_id="nhs-autism",
            source_item_id="signs",
            url="https://example.test/signs",
            content_type_header="text/html",
            payload=_HTML.encode("utf-8"),
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )
        doc = build_parsed_document(
            raw,
            source_id="nhs-autism",
            licence="OGL-UK-3.0",
            licence_url="x",
            attribution="x",
            content_type="patient-info",
            medical_disclaimer_required=False,
            payload_kind="html",
            title_override="Custom Title",
        )
        assert doc.title == "Custom Title"


class TestHttpGetAsRawDocument:
    @respx.mock
    def test_wraps_get_in_raw_document(self, tmp_path: Path) -> None:
        respx.get("https://example.test/a").mock(
            return_value=httpx.Response(200, text="hello", headers={"content-type": "text/html"})
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        raw = http_get_as_raw_document(
            client,
            source_id="nhs-autism",
            source_item_id="a",
            url="https://example.test/a",
        )
        assert raw.payload == b"hello"
        assert raw.source_id == "nhs-autism"
        assert raw.source_item_id == "a"
        assert raw.url == "https://example.test/a"
        assert raw.content_type_header is not None
        assert raw.content_type_header.startswith("text/html")
