from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from autism_corpus.adapters.base import SourceAdapter
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.pipeline import BuildResult, run_build
from autism_corpus.utils.hashing import canonical_text_hash
from autism_corpus.utils.http import CachedHttpClient


def _doc(
    source_id: str,
    item_id: str,
    title: str,
    body: str,
    *,
    licence: str = "public-domain",
    content_type: str = "patient-info",
    last_modified_at: date | None = None,
) -> ParsedDocument:
    text = f"# {title}\n\n{body}"
    return ParsedDocument(
        source_id=source_id,
        source_item_id=item_id,
        canonical_url=f"https://example.test/{source_id}/{item_id}",
        title=title,
        text=text,
        language="en",
        published_at=None,
        last_modified_at=last_modified_at,
        licence=licence,
        licence_url="https://example.test/licence",
        attribution=f"{source_id} attribution",
        content_type=content_type,  # type: ignore[arg-type]
        medical_disclaimer_required=False,
        hash=canonical_text_hash(text),
        fetched_at=datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
    )


class _StubAdapter(SourceAdapter):
    """Adapter that yields pre-built ParsedDocuments, bypassing http/parse.

    The pipeline only needs discover/fetch/parse for online runs. For tests we
    short-circuit by overriding parse() to return a stashed doc keyed by ref.
    """

    source_id = "stub-source"
    licence = "public-domain"
    licence_url = "https://example.test/licence"
    attribution_template = "Stub source"

    def __init__(self, http_client: CachedHttpClient, docs: list[ParsedDocument]) -> None:
        super().__init__(http_client)
        self._docs = {d.source_item_id: d for d in docs}

    def discover(self) -> Iterator[SourceItemRef]:
        for item_id in self._docs:
            yield SourceItemRef(source_id=self.source_id, item_id=item_id)

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        return RawDocument(
            source_id=self.source_id,
            source_item_id=ref.item_id,
            url=self._docs[ref.item_id].canonical_url,
            content_type_header="text/html",
            payload=self._docs[ref.item_id].text.encode("utf-8"),
            fetched_at=datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
        )

    def parse(self, raw: RawDocument) -> ParsedDocument:
        return self._docs[raw.source_item_id]


class _OtherStubAdapter(_StubAdapter):
    source_id = "other-stub"
    licence = "CC-BY-4.0"
    licence_url = "https://creativecommons.org/licenses/by/4.0/"
    attribution_template = "Other stub source"


@pytest.fixture
def http_client(tmp_path: Path) -> CachedHttpClient:
    return CachedHttpClient(source_id="stub", cache_dir=tmp_path / "cache")


class TestRunBuild:
    def test_writes_documents_chunks_manifest(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        docs = [
            _doc("stub-source", "a", "First Article", " ".join(["alpha"] * 400)),
            _doc("stub-source", "b", "Second Article", " ".join(["beta"] * 400)),
        ]
        adapter = _StubAdapter(http_client, docs)
        result = run_build(
            [adapter],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub"},
        )

        assert result.run_id == "testrun"
        assert result.documents_path.exists()
        assert result.chunks_path.exists()
        assert result.manifest_path.exists()

        doc_lines = result.documents_path.read_text().strip().splitlines()
        chunk_lines = result.chunks_path.read_text().strip().splitlines()
        assert len(doc_lines) == 2
        assert len(chunk_lines) >= 2

        first_chunk = json.loads(chunk_lines[0])
        assert first_chunk["source_id"] == "stub-source"
        assert first_chunk["breadcrumb"].startswith("Stub")
        assert "licence" in first_chunk
        assert "attribution" in first_chunk
        assert "canonical_url" in first_chunk

    def test_manifest_aggregates_per_source_and_licence(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        docs_a = [_doc("stub-source", "a", "A", " ".join(["x"] * 400))]
        docs_b = [
            _doc("other-stub", "b", "B", " ".join(["y"] * 400), licence="CC-BY-4.0"),
        ]
        result = run_build(
            [
                _StubAdapter(http_client, docs_a),
                _OtherStubAdapter(http_client, docs_b),
            ],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub", "other-stub": "Other"},
        )
        manifest = json.loads(result.manifest_path.read_text())
        assert set(manifest["sources"].keys()) == {"stub-source", "other-stub"}
        assert manifest["sources"]["stub-source"]["documents"] == 1
        assert manifest["sources"]["other-stub"]["documents"] == 1
        assert set(manifest["licences"].keys()) == {"public-domain", "CC-BY-4.0"}

    def test_dedup_drops_identical_text(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        # Same text under two different source_ids; same canonical hash -> dedup keeps the
        # cleaner licence (public-domain over CC-BY-4.0).
        same_text = " ".join(["dup"] * 400)
        docs_a = [_doc("stub-source", "x", "Title", same_text)]
        docs_b = [_doc("other-stub", "y", "Title", same_text, licence="CC-BY-4.0")]

        result = run_build(
            [
                _StubAdapter(http_client, docs_a),
                _OtherStubAdapter(http_client, docs_b),
            ],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub", "other-stub": "Other"},
        )
        doc_lines = result.documents_path.read_text().strip().splitlines()
        assert len(doc_lines) == 1
        kept = json.loads(doc_lines[0])
        assert kept["licence"] == "public-domain"

    def test_filters_drop_too_short(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        # 10-token doc should be filtered out (under 200-token min).
        docs = [
            _doc("stub-source", "tiny", "Tiny", "this is a very short text"),
            _doc("stub-source", "big", "Big", " ".join(["word"] * 400)),
        ]
        result = run_build(
            [_StubAdapter(http_client, docs)],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub"},
        )
        doc_lines = result.documents_path.read_text().strip().splitlines()
        item_ids = {json.loads(line)["source_item_id"] for line in doc_lines}
        assert item_ids == {"big"}

    def test_chunks_carry_provenance(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        docs = [_doc("stub-source", "a", "Title", " ".join(["alpha"] * 400))]
        result = run_build(
            [_StubAdapter(http_client, docs)],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub"},
        )
        for line in result.chunks_path.read_text().strip().splitlines():
            chunk = json.loads(line)
            assert chunk["licence"]
            assert chunk["attribution"]
            assert chunk["canonical_url"]
            assert chunk["breadcrumb"]
            assert chunk["token_count"] > 0

    def test_reproducible(self, http_client: CachedHttpClient, tmp_path: Path) -> None:
        docs = [_doc("stub-source", "a", "Title", " ".join(["alpha"] * 400))]
        result1 = run_build(
            [_StubAdapter(http_client, docs)],
            output_root=tmp_path / "out1",
            run_id="run1",
            site_prefixes={"stub-source": "Stub"},
        )
        result2 = run_build(
            [_StubAdapter(http_client, docs)],
            output_root=tmp_path / "out2",
            run_id="run2",
            site_prefixes={"stub-source": "Stub"},
        )
        # chunks should be identical except for fetched_at and run-level metadata in manifest
        c1 = [json.loads(line) for line in result1.chunks_path.read_text().splitlines()]
        c2 = [json.loads(line) for line in result2.chunks_path.read_text().splitlines()]
        for a, b in zip(c1, c2, strict=True):
            a.pop("fetched_at", None)
            b.pop("fetched_at", None)
        assert c1 == c2

    def test_returns_build_result(
        self, http_client: CachedHttpClient, tmp_path: Path
    ) -> None:
        docs = [_doc("stub-source", "a", "Title", " ".join(["alpha"] * 400))]
        result = run_build(
            [_StubAdapter(http_client, docs)],
            output_root=tmp_path / "output",
            run_id="testrun",
            site_prefixes={"stub-source": "Stub"},
        )
        assert isinstance(result, BuildResult)
        assert len(result.documents) == 1
        assert len(result.chunks) >= 1
        assert result.manifest.run_id == "testrun"
