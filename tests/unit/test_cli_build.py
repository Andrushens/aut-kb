from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autism_corpus.adapters.base import SourceAdapter
from autism_corpus.cli import app
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.hashing import canonical_text_hash
from autism_corpus.utils.http import CachedHttpClient


class _IsolatedAdapter(SourceAdapter):
    """Adapter used only by these CLI tests, kept out of the global registry."""

    source_id = "cli-test-source"
    licence = "public-domain"
    licence_url = "https://example.test/licence"
    attribution_template = "CLI test"

    def __init__(self, http_client: CachedHttpClient, payload: str) -> None:
        super().__init__(http_client)
        self._payload = payload

    def discover(self) -> Iterator[SourceItemRef]:
        yield SourceItemRef(source_id=self.source_id, item_id="doc")

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        return RawDocument(
            source_id=self.source_id,
            source_item_id=ref.item_id,
            url=f"https://example.test/{ref.item_id}",
            content_type_header="text/plain",
            payload=self._payload.encode("utf-8"),
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )

    def parse(self, raw: RawDocument) -> ParsedDocument:
        text = raw.payload.decode("utf-8")
        return ParsedDocument(
            source_id=self.source_id,
            source_item_id=raw.source_item_id,
            canonical_url=raw.url,
            title="CLI Test",
            text=text,
            language="en",
            published_at=None,
            last_modified_at=None,
            licence=self.licence,
            licence_url=self.licence_url,
            attribution=self.attribution_template,
            content_type="patient-info",
            medical_disclaimer_required=False,
            hash=canonical_text_hash(text),
            fetched_at=raw.fetched_at,
        )


@pytest.fixture
def patched_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> CachedHttpClient:
    client = CachedHttpClient(source_id="cli-test-source", cache_dir=tmp_path / "cache")
    payload = " ".join(["alpha"] * 400)
    adapter = _IsolatedAdapter(client, payload)
    monkeypatch.setattr(
        "autism_corpus.cli._build_registered_adapters",
        lambda *_, **__: [adapter],
    )
    return client


class TestBuildCommand:
    def test_build_all_produces_chunks_and_report(
        self, patched_registry: CachedHttpClient, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        out_root = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "build",
                "--all",
                "--run-id",
                "testrun",
                "--output-root",
                str(out_root),
            ],
        )
        assert result.exit_code == 0, result.stdout
        chunks_path = out_root / "testrun" / "chunks.jsonl"
        documents_path = out_root / "testrun" / "documents.jsonl"
        manifest_path = out_root / "testrun" / "manifest.json"
        report_path = out_root / "testrun" / "report.html"

        assert chunks_path.exists()
        assert documents_path.exists()
        assert manifest_path.exists()
        assert report_path.exists()
        assert chunks_path.read_text().strip(), "chunks.jsonl is empty"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == "testrun"
        assert "cli-test-source" in manifest["sources"]


class TestReportCommand:
    def test_report_regenerates_html(
        self, patched_registry: CachedHttpClient, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        out_root = tmp_path / "output"
        runner.invoke(
            app,
            [
                "build",
                "--all",
                "--run-id",
                "testrun",
                "--output-root",
                str(out_root),
            ],
        )
        report_path = out_root / "testrun" / "report.html"
        report_path.unlink()
        result = runner.invoke(
            app,
            [
                "report",
                "--run-id",
                "testrun",
                "--output-root",
                str(out_root),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert report_path.exists()
        assert "testrun" in report_path.read_text()
