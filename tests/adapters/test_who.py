from __future__ import annotations

from pathlib import Path

import httpx
import pymupdf
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.who import WhoAutismAdapter
from autism_corpus.utils.http import CachedHttpClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "who"


def _html_fixture() -> bytes:
    return (FIXTURES / "autism-fact-sheet.html").read_bytes()


def _make_pdf(body_text: str, *, title: str | None = None) -> bytes:
    doc = pymupdf.open()
    if title is not None:
        doc.set_metadata({"title": title})
    page = doc.new_page()
    page.insert_text((72, 120), body_text, fontsize=12)
    return bytes(doc.tobytes())


class TestWhoAutismAdapterRegistration:
    def test_registered_under_source_id(self) -> None:
        assert adapter_registry()["who-autism"] is WhoAutismAdapter

    def test_class_attributes(self) -> None:
        assert WhoAutismAdapter.source_id == "who-autism"
        assert WhoAutismAdapter.licence == "CC-BY-NC-SA-3.0-IGO"
        assert WhoAutismAdapter.licence_url == (
            "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"
        )
        assert WhoAutismAdapter.attribution_template == (
            "World Health Organization, licenced under CC BY-NC-SA 3.0 IGO"
        )


class TestWhoAutismAdapterDiscover:
    def test_yields_refs_from_seed_yaml(self, tmp_path: Path) -> None:
        client = CachedHttpClient(source_id="who-autism", cache_dir=tmp_path)
        adapter = WhoAutismAdapter(http_client=client)

        refs = list(adapter.discover())

        item_ids = {r.item_id for r in refs}
        assert "autism-spectrum-disorders" in item_ids
        assert "autism-fact-sheet-pdf" in item_ids
        for ref in refs:
            assert ref.source_id == "who-autism"
            assert ref.url is not None


class TestWhoAutismAdapterFetchAndParseHtml:
    @respx.mock
    def test_parse_html_branch(self, tmp_path: Path) -> None:
        respx.get("https://example.test/who-autism.html").mock(
            return_value=httpx.Response(
                200, content=_html_fixture(), headers={"content-type": "text/html"}
            )
        )
        client = CachedHttpClient(source_id="who-autism", cache_dir=tmp_path)
        adapter = WhoAutismAdapter(http_client=client)
        ref = next(r for r in adapter.discover() if r.item_id == "autism-spectrum-disorders")

        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "who-autism"
        assert doc.source_item_id == "autism-spectrum-disorders"
        assert doc.canonical_url == "https://example.test/who-autism.html"
        assert doc.licence == "CC-BY-NC-SA-3.0-IGO"
        assert doc.licence_url == "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"
        assert doc.attribution == (
            "World Health Organization, licenced under CC BY-NC-SA 3.0 IGO"
        )
        assert doc.content_type == "fact-sheet"
        assert doc.medical_disclaimer_required is False
        assert "Autism" in doc.title or "autism" in doc.title.lower()
        assert "autism" in doc.text.lower()
        assert len(doc.hash) == 64


class TestWhoAutismAdapterFetchAndParsePdf:
    @respx.mock
    def test_parse_pdf_branch(self, tmp_path: Path) -> None:
        pdf_bytes = _make_pdf(
            "WHO fact sheet on autism spectrum disorders for global health reporting.",
            title="Autism fact sheet",
        )
        respx.get("https://example.test/who-autism.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        )
        client = CachedHttpClient(source_id="who-autism", cache_dir=tmp_path)
        adapter = WhoAutismAdapter(http_client=client)
        ref = next(r for r in adapter.discover() if r.item_id == "autism-fact-sheet-pdf")

        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "who-autism"
        assert doc.source_item_id == "autism-fact-sheet-pdf"
        assert doc.canonical_url == "https://example.test/who-autism.pdf"
        assert doc.licence == "CC-BY-NC-SA-3.0-IGO"
        assert doc.attribution == (
            "World Health Organization, licenced under CC BY-NC-SA 3.0 IGO"
        )
        assert doc.content_type == "fact-sheet"
        assert doc.medical_disclaimer_required is False
        assert "autism" in doc.text.lower()
        assert len(doc.hash) == 64
