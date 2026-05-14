from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from autism_corpus.models import (
    Chunk,
    ContentType,
    Manifest,
    ParsedDocument,
    RawDocument,
    SourceItemRef,
)


def _parsed_doc_kwargs() -> dict:
    return {
        "source_id": "nhs-autism",
        "source_item_id": "signs-in-toddlers",
        "canonical_url": "https://www.nhs.uk/conditions/autism/signs/children/",
        "title": "Signs of autism in young children",
        "text": "## Signs in toddlers\n\nAutistic toddlers may...",
        "language": "en",
        "published_at": date(2023, 4, 12),
        "last_modified_at": date(2024, 1, 1),
        "licence": "OGL-UK-3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "attribution": "Information from NHS Digital, licenced under OGL v3.0",
        "content_type": "patient-info",
        "medical_disclaimer_required": False,
        "hash": "a" * 64,
        "fetched_at": datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
    }


class TestSourceItemRef:
    def test_minimum_fields_round_trip(self) -> None:
        ref = SourceItemRef(source_id="nhs-autism", item_id="signs-in-toddlers")
        assert ref.source_id == "nhs-autism"
        assert ref.item_id == "signs-in-toddlers"
        round_tripped = SourceItemRef.model_validate_json(ref.model_dump_json())
        assert round_tripped == ref

    def test_optional_url(self) -> None:
        ref = SourceItemRef(
            source_id="nhs-autism",
            item_id="signs-in-toddlers",
            url="https://example.com/x",
        )
        assert ref.url == "https://example.com/x"


class TestRawDocument:
    def test_payload_bytes_round_trip(self) -> None:
        raw = RawDocument(
            source_id="nhs-autism",
            source_item_id="signs",
            url="https://www.nhs.uk/conditions/autism/signs/",
            content_type_header="text/html; charset=utf-8",
            payload=b"<html><body>hello</body></html>",
            fetched_at=datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
        )
        as_json = raw.model_dump_json()
        # Ensure the bytes survived (base64-encoded in JSON, but round-trippable)
        again = RawDocument.model_validate_json(as_json)
        assert again.payload == raw.payload


class TestParsedDocument:
    def test_round_trip_json(self) -> None:
        doc = ParsedDocument(**_parsed_doc_kwargs())
        again = ParsedDocument.model_validate_json(doc.model_dump_json())
        assert again == doc

    def test_attribution_required(self) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs.pop("attribution")
        with pytest.raises(ValidationError):
            ParsedDocument(**kwargs)

    def test_licence_required(self) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs.pop("licence")
        with pytest.raises(ValidationError):
            ParsedDocument(**kwargs)

    def test_canonical_url_required(self) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs.pop("canonical_url")
        with pytest.raises(ValidationError):
            ParsedDocument(**kwargs)

    def test_hash_must_be_64_hex(self) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs["hash"] = "not-a-sha256"
        with pytest.raises(ValidationError):
            ParsedDocument(**kwargs)

    def test_content_type_literal(self) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs["content_type"] = "not-a-content-type"
        with pytest.raises(ValidationError):
            ParsedDocument(**kwargs)

    @pytest.mark.parametrize(
        "content_type",
        [
            "patient-info",
            "clinical-guideline",
            "research-article",
            "fact-sheet",
            "toolkit",
        ],
    )
    def test_content_type_accepts_known_values(self, content_type: ContentType) -> None:
        kwargs = _parsed_doc_kwargs()
        kwargs["content_type"] = content_type
        doc = ParsedDocument(**kwargs)
        assert doc.content_type == content_type

    def test_document_id_property(self) -> None:
        doc = ParsedDocument(**_parsed_doc_kwargs())
        assert doc.document_id == "nhs-autism::signs-in-toddlers"


class TestChunk:
    def _chunk_kwargs(self) -> dict:
        return {
            "chunk_id": "nhs-autism::signs-in-toddlers::0003",
            "document_id": "nhs-autism::signs-in-toddlers",
            "source_id": "nhs-autism",
            "canonical_url": "https://www.nhs.uk/conditions/autism/signs/children/",
            "title": "Signs of autism in young children",
            "breadcrumb": "NHS > Signs of autism > Signs in young children > Signs in toddlers",
            "text": "## Signs in toddlers\n\nAutistic toddlers may...",
            "token_count": 412,
            "language": "en",
            "licence": "OGL-UK-3.0",
            "attribution": "Information from NHS Digital, licenced under OGL v3.0",
            "content_type": "patient-info",
            "medical_disclaimer_required": False,
            "published_at": date(2023, 4, 12),
            "fetched_at": datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
        }

    def test_round_trip_json(self) -> None:
        chunk = Chunk(**self._chunk_kwargs())
        again = Chunk.model_validate_json(chunk.model_dump_json())
        assert again == chunk

    def test_chunk_id_starts_with_document_id(self) -> None:
        kwargs = self._chunk_kwargs()
        kwargs["chunk_id"] = "unrelated::id::0001"
        with pytest.raises(ValidationError):
            Chunk(**kwargs)

    def test_token_count_positive(self) -> None:
        kwargs = self._chunk_kwargs()
        kwargs["token_count"] = 0
        with pytest.raises(ValidationError):
            Chunk(**kwargs)

    def test_breadcrumb_required_non_empty(self) -> None:
        kwargs = self._chunk_kwargs()
        kwargs["breadcrumb"] = ""
        with pytest.raises(ValidationError):
            Chunk(**kwargs)


class TestManifest:
    def test_aggregates_counts_per_source(self) -> None:
        manifest = Manifest(
            run_id="2026-05-14T09-00-00",
            pipeline_version="0.1.0",
            sources={
                "nhs-autism": {"documents": 50, "chunks": 412},
                "cdc-autism": {"documents": 70, "chunks": 530},
            },
            licences={"OGL-UK-3.0": 412, "public-domain": 530},
            input_hash="b" * 64,
            generated_at=datetime(2026, 5, 14, 9, 5, 0, tzinfo=UTC),
        )
        again = Manifest.model_validate_json(manifest.model_dump_json())
        assert again == manifest
        assert again.total_chunks == 942
        assert again.total_documents == 120
