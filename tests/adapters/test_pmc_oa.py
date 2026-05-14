from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.pmc_oa import (
    ArticleLoader,
    FileListEntry,
    PmcOaAdapter,
    PmcSkip,
)
from autism_corpus.models import RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pmc"


def _read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _load_file_list_entries() -> list[FileListEntry]:
    """Load synthetic file_list CSV fixture into FileListEntry rows."""
    rows: list[FileListEntry] = []
    article_type_by_pmcid = {
        "PMC1234567": "review-article",
        "PMC2222222": "research-article",
        "PMC3333333": "review-article",
        "PMC4444444": "review-article",
        "PMC5555555": "review-article",
    }
    with (FIXTURES / "sample_file_list_excerpt.csv").open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            pmcid = row["AccessionID"]
            rows.append(
                FileListEntry(
                    pmcid=pmcid,
                    article_file=row["File"],
                    licence=row["License"],
                    article_type=article_type_by_pmcid[pmcid],
                    mesh_terms=[],
                )
            )
    return rows


def _fixture_loader_for(mapping: dict[str, str]) -> ArticleLoader:
    """Build an article_loader callable that returns the fixture bytes
    matching the entry's pmcid."""

    def _loader(entry: FileListEntry) -> bytes:
        fname = mapping[entry.pmcid]
        return _read_fixture(fname)

    return _loader


def _adapter(
    tmp_path: Path,
    *,
    entries: Iterable[FileListEntry],
    loader_mapping: dict[str, str],
) -> PmcOaAdapter:
    client = CachedHttpClient(source_id="pmc-oa-autism", cache_dir=tmp_path)
    entries_list = list(entries)
    return PmcOaAdapter(
        http_client=client,
        file_list_source=lambda: iter(entries_list),
        article_loader=_fixture_loader_for(loader_mapping),
    )


class TestPmcOaDiscover:
    def test_pmc_oa_drops_primary_research_article_type(self, tmp_path: Path) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="x.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC2222222",
                article_file="y.tar.gz",
                licence="CC BY",
                article_type="research-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC9999991",
                article_file="z.tar.gz",
                licence="CC BY",
                article_type="systematic-review",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path,
            entries=entries,
            loader_mapping={},  # discover() does not invoke loader
        )
        refs = list(adapter.discover())
        item_ids = {ref.item_id for ref in refs}
        assert "PMC1234567" in item_ids
        assert "PMC9999991" in item_ids
        assert "PMC2222222" not in item_ids

    def test_pmc_oa_drops_non_commercial_and_unknown_licences(
        self, tmp_path: Path
    ) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="x.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC3333333",
                article_file="y.tar.gz",
                licence="CC BY-NC",
                article_type="review-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC5555555",
                article_file="z.tar.gz",
                licence="NO-CC",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path, entries=entries, loader_mapping={}
        )
        refs = list(adapter.discover())
        item_ids = {ref.item_id for ref in refs}
        assert item_ids == {"PMC1234567"}

    def test_pmc_oa_discover_does_not_run_autism_keyword_filter(
        self, tmp_path: Path
    ) -> None:
        # The autism MeSH/keyword filter requires the article body, so
        # discover() must NOT raise on entries whose mesh_terms are empty.
        entries = [
            FileListEntry(
                pmcid="PMC4444444",
                article_file="x.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path, entries=entries, loader_mapping={}
        )
        refs = list(adapter.discover())  # must not raise
        assert len(refs) == 1
        assert refs[0].item_id == "PMC4444444"

    def test_pmc_oa_discover_yields_source_item_ref_with_source_id(
        self, tmp_path: Path
    ) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="x.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path, entries=entries, loader_mapping={}
        )
        ref = next(iter(adapter.discover()))
        assert ref.source_id == "pmc-oa-autism"


class TestPmcOaParse:
    def _make_raw(self, pmcid: str, xml_name: str) -> RawDocument:
        return RawDocument(
            source_id="pmc-oa-autism",
            source_item_id=pmcid,
            url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
            content_type_header="application/xml",
            payload=_read_fixture(xml_name),
            fetched_at=datetime(2026, 5, 14, tzinfo=UTC),
        )

    def _adapter_no_loader(self, tmp_path: Path) -> PmcOaAdapter:
        client = CachedHttpClient(source_id="pmc-oa-autism", cache_dir=tmp_path)
        return PmcOaAdapter(
            http_client=client,
            file_list_source=lambda: iter(()),
            article_loader=lambda _entry: b"",
        )

    def test_pmc_oa_parse_extracts_title_and_body(self, tmp_path: Path) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert doc.title == "A review of autism spectrum disorder interventions"
        assert "Introduction" in doc.text
        assert "Autism spectrum disorder is a developmental condition" in doc.text
        assert "Methods" in doc.text
        assert "behavioural interventions" in doc.text

    def test_pmc_oa_parse_skips_when_no_autism_keywords(
        self, tmp_path: Path
    ) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC4444444", "sample_review_no_autism.xml")
        with pytest.raises(PmcSkip):
            adapter.parse(raw)

    def test_pmc_oa_parse_maps_per_article_licence_to_spdx(
        self, tmp_path: Path
    ) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert doc.licence == "CC-BY-4.0"
        assert doc.licence_url == "https://creativecommons.org/licenses/by/4.0/"

    def test_pmc_oa_parse_sets_canonical_pmc_url(self, tmp_path: Path) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert (
            doc.canonical_url
            == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/"
        )

    def test_pmc_oa_parse_fills_attribution_template_with_spdx_licence(
        self, tmp_path: Path
    ) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert doc.attribution == "PubMed Central Open Access (CC-BY-4.0)"

    def test_pmc_oa_parse_sets_published_at_from_pub_date(
        self, tmp_path: Path
    ) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert doc.published_at is not None
        assert doc.published_at.isoformat() == "2022-03-15"

    def test_pmc_oa_parse_marks_medical_disclaimer_required(
        self, tmp_path: Path
    ) -> None:
        adapter = self._adapter_no_loader(tmp_path)
        raw = self._make_raw("PMC1234567", "sample_review_cc_by.xml")
        doc = adapter.parse(raw)
        assert doc.medical_disclaimer_required is True
        assert doc.content_type == "research-article"


class TestPmcOaEndToEnd:
    def test_pmc_oa_full_pipeline_with_three_entries(self, tmp_path: Path) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="oa_package/00/01/PMC1234567.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC2222222",
                article_file="oa_package/00/02/PMC2222222.tar.gz",
                licence="CC BY",
                article_type="research-article",
                mesh_terms=[],
            ),
            FileListEntry(
                pmcid="PMC3333333",
                article_file="oa_package/00/03/PMC3333333.tar.gz",
                licence="CC BY-NC",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path,
            entries=entries,
            loader_mapping={
                "PMC1234567": "sample_review_cc_by.xml",
                "PMC2222222": "sample_primary_research_cc_by.xml",
                "PMC3333333": "sample_review_cc_by_nc.xml",
            },
        )

        refs = list(adapter.discover())
        assert len(refs) == 1
        assert refs[0].item_id == "PMC1234567"

        raw = adapter.fetch(refs[0])
        assert raw.payload == _read_fixture("sample_review_cc_by.xml")
        assert raw.source_id == "pmc-oa-autism"
        assert raw.source_item_id == "PMC1234567"
        assert raw.content_type_header == "application/xml"

        doc = adapter.parse(raw)
        assert doc.licence == "CC-BY-4.0"
        assert doc.content_type == "research-article"
        assert doc.source_id == "pmc-oa-autism"


class TestPmcOaFromFileListCsv:
    def test_pmc_oa_uses_real_csv_excerpt_as_file_list_source(
        self, tmp_path: Path
    ) -> None:
        # The CSV fixture has five entries; discover() should drop the
        # primary-research one (PMC2222222), the CC-BY-NC one (PMC3333333),
        # and the unknown-licence one (PMC5555555). Two review-articles with
        # CC BY remain at discover() (PMC1234567 + PMC4444444); the
        # autism-keyword filter only fires at parse-time.
        entries = _load_file_list_entries()
        client = CachedHttpClient(source_id="pmc-oa-autism", cache_dir=tmp_path)
        adapter = PmcOaAdapter(
            http_client=client,
            file_list_source=lambda: iter(entries),
            article_loader=_fixture_loader_for(
                {"PMC1234567": "sample_review_cc_by.xml"}
            ),
        )
        refs = list(adapter.discover())
        assert {r.item_id for r in refs} == {"PMC1234567", "PMC4444444"}


class TestPmcOaFetch:
    def test_pmc_oa_fetch_returns_xml_bytes_for_matching_entry(
        self, tmp_path: Path
    ) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="oa_package/00/01/PMC1234567.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path,
            entries=entries,
            loader_mapping={"PMC1234567": "sample_review_cc_by.xml"},
        )
        ref = SourceItemRef(source_id="pmc-oa-autism", item_id="PMC1234567")
        raw = adapter.fetch(ref)
        assert raw.source_item_id == "PMC1234567"
        assert raw.payload == _read_fixture("sample_review_cc_by.xml")
        assert raw.content_type_header == "application/xml"

    def test_pmc_oa_fetch_raises_keyerror_for_unknown_pmcid(
        self, tmp_path: Path
    ) -> None:
        entries = [
            FileListEntry(
                pmcid="PMC1234567",
                article_file="x.tar.gz",
                licence="CC BY",
                article_type="review-article",
                mesh_terms=[],
            ),
        ]
        adapter = _adapter(
            tmp_path,
            entries=entries,
            loader_mapping={"PMC1234567": "sample_review_cc_by.xml"},
        )
        ref = SourceItemRef(source_id="pmc-oa-autism", item_id="PMC0000000")
        with pytest.raises(KeyError):
            adapter.fetch(ref)


class TestPmcOaRegistry:
    def test_pmc_oa_adapter_registered(self) -> None:
        assert adapter_registry()["pmc-oa-autism"] is PmcOaAdapter
