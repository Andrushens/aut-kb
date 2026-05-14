from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from autism_corpus.filters import FilterReport
from autism_corpus.models import Chunk, Manifest, ParsedDocument
from autism_corpus.pipeline import BuildResult, SourceStats
from autism_corpus.report import render_report, write_report
from autism_corpus.utils.hashing import canonical_text_hash


def _make_result(tmp_path: Path) -> BuildResult:
    text = " ".join(["alpha"] * 100)
    doc = ParsedDocument(
        source_id="nhs-autism",
        source_item_id="signs",
        canonical_url="https://www.nhs.uk/conditions/autism/signs/",
        title="Signs of autism",
        text=text,
        language="en",
        published_at=None,
        last_modified_at=None,
        licence="OGL-UK-3.0",
        licence_url="https://example.test/ogl",
        attribution="NHS",
        content_type="patient-info",
        medical_disclaimer_required=False,
        hash=canonical_text_hash(text),
        fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
    )
    chunk = Chunk(
        chunk_id=f"{doc.document_id}::0000",
        document_id=doc.document_id,
        source_id=doc.source_id,
        canonical_url=doc.canonical_url,
        title=doc.title,
        breadcrumb="NHS > Signs of autism",
        text="NHS > Signs of autism\n\n" + text,
        token_count=120,
        language="en",
        licence=doc.licence,
        attribution=doc.attribution,
        content_type=doc.content_type,
        medical_disclaimer_required=False,
        published_at=None,
        fetched_at=doc.fetched_at,
    )
    manifest = Manifest(
        run_id="testrun",
        pipeline_version="0.1.0",
        sources={"nhs-autism": {"documents": 1, "chunks": 1, "discovered": 1, "parse_errors": 0}},
        licences={"OGL-UK-3.0": 1},
        input_hash=canonical_text_hash("input"),
        generated_at=datetime(2026, 5, 14, tzinfo=UTC),
    )
    output_dir = tmp_path / "testrun"
    output_dir.mkdir(parents=True)
    return BuildResult(
        run_id="testrun",
        output_dir=output_dir,
        documents_path=output_dir / "documents.jsonl",
        chunks_path=output_dir / "chunks.jsonl",
        manifest_path=output_dir / "manifest.json",
        report_path=output_dir / "report.html",
        documents=[doc],
        chunks=[chunk],
        manifest=manifest,
        filter_report=FilterReport(kept=[doc], dropped=[], flagged_for_review=[]),
        per_source={
            "nhs-autism": SourceStats(
                documents_discovered=1,
                documents_parsed=1,
                documents_kept=1,
                chunks_emitted=1,
            )
        },
    )


class TestRenderReport:
    def test_contains_run_id_and_version(self, tmp_path: Path) -> None:
        html = render_report(_make_result(tmp_path))
        assert "testrun" in html
        assert "0.1.0" in html

    def test_contains_per_source_breakdown(self, tmp_path: Path) -> None:
        html = render_report(_make_result(tmp_path))
        assert "nhs-autism" in html
        assert "Documents" in html or "documents" in html.lower()
        assert "Chunks" in html or "chunks" in html.lower()

    def test_contains_licence_breakdown(self, tmp_path: Path) -> None:
        html = render_report(_make_result(tmp_path))
        assert "OGL-UK-3.0" in html

    def test_escapes_html_in_titles(self, tmp_path: Path) -> None:
        result = _make_result(tmp_path)
        nasty_doc = result.documents[0].model_copy(update={"title": "<script>alert(1)</script>"})
        result = BuildResult(
            run_id=result.run_id,
            output_dir=result.output_dir,
            documents_path=result.documents_path,
            chunks_path=result.chunks_path,
            manifest_path=result.manifest_path,
            report_path=result.report_path,
            documents=[nasty_doc],
            chunks=result.chunks,
            manifest=result.manifest,
            filter_report=result.filter_report,
            per_source=result.per_source,
        )
        html = render_report(result)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestWriteReport:
    def test_writes_to_report_path(self, tmp_path: Path) -> None:
        result = _make_result(tmp_path)
        write_report(result)
        assert result.report_path.exists()
        body = result.report_path.read_text()
        assert "testrun" in body
        assert "nhs-autism" in body
