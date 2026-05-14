from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autism_corpus.adapters.base import (
    SourceAdapter,
    adapter_registry,
    register_adapter,
)
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient


class _FakeAdapter(SourceAdapter):
    source_id = "fake-source"
    licence = "public-domain"
    licence_url = "https://example.test/licence"
    attribution_template = "Fake Source attribution"

    def discover(self) -> Iterator[SourceItemRef]:
        yield SourceItemRef(source_id=self.source_id, item_id="a")

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        return RawDocument(
            source_id=self.source_id,
            source_item_id=ref.item_id,
            url=ref.url or "https://example.test/a",
            content_type_header="text/html",
            payload=b"<html/>",
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )

    def parse(self, raw: RawDocument) -> ParsedDocument:
        return ParsedDocument(
            source_id=raw.source_id,
            source_item_id=raw.source_item_id,
            canonical_url=raw.url,
            title="Fake",
            text="some content here",
            language="en",
            published_at=None,
            last_modified_at=None,
            licence=self.licence,
            licence_url=self.licence_url,
            attribution=self.attribution_template,
            content_type="fact-sheet",
            medical_disclaimer_required=False,
            hash="0" * 64,
            fetched_at=raw.fetched_at,
        )


class TestSourceAdapterContract:
    def test_subclass_must_set_source_id(self) -> None:
        class _Bad(SourceAdapter):
            licence = "public-domain"
            licence_url = "x"
            attribution_template = "y"

            def discover(self) -> Iterator[SourceItemRef]:
                return iter([])

            def fetch(self, ref: SourceItemRef) -> RawDocument:
                raise NotImplementedError

            def parse(self, raw: RawDocument) -> ParsedDocument:
                raise NotImplementedError

        with pytest.raises(TypeError):
            _Bad()

    def test_fake_adapter_roundtrip(self, tmp_path: Path) -> None:
        client = CachedHttpClient(source_id="fake-source", cache_dir=tmp_path)
        adapter = _FakeAdapter(http_client=client)
        refs = list(adapter.discover())
        assert refs[0].source_id == "fake-source"
        raw = adapter.fetch(refs[0])
        doc = adapter.parse(raw)
        assert doc.source_id == "fake-source"
        assert doc.licence == "public-domain"

    def test_adapter_carries_http_client(self, tmp_path: Path) -> None:
        client = CachedHttpClient(source_id="fake-source", cache_dir=tmp_path)
        adapter = _FakeAdapter(http_client=client)
        assert adapter.http_client is client


class TestAdapterRegistry:
    def test_register_and_lookup(self) -> None:
        @register_adapter
        class _RegMe(SourceAdapter):
            source_id = "reg-test-1"
            licence = "public-domain"
            licence_url = "x"
            attribution_template = "y"

            def discover(self) -> Iterator[SourceItemRef]:
                return iter([])

            def fetch(self, ref: SourceItemRef) -> RawDocument:
                raise NotImplementedError

            def parse(self, raw: RawDocument) -> ParsedDocument:
                raise NotImplementedError

        assert adapter_registry()["reg-test-1"] is _RegMe

    def test_duplicate_registration_rejected(self) -> None:
        @register_adapter
        class _RegOnce(SourceAdapter):
            source_id = "reg-test-2"
            licence = "public-domain"
            licence_url = "x"
            attribution_template = "y"

            def discover(self) -> Iterator[SourceItemRef]:
                return iter([])

            def fetch(self, ref: SourceItemRef) -> RawDocument:
                raise NotImplementedError

            def parse(self, raw: RawDocument) -> ParsedDocument:
                raise NotImplementedError

        with pytest.raises(ValueError, match="reg-test-2"):

            @register_adapter
            class _RegTwice(SourceAdapter):
                source_id = "reg-test-2"
                licence = "public-domain"
                licence_url = "x"
                attribution_template = "y"

                def discover(self) -> Iterator[SourceItemRef]:
                    return iter([])

                def fetch(self, ref: SourceItemRef) -> RawDocument:
                    raise NotImplementedError

                def parse(self, raw: RawDocument) -> ParsedDocument:
                    raise NotImplementedError
