from __future__ import annotations

from pathlib import Path

import httpx
import pymupdf
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.nice_guidelines import NiceGuidelinesAdapter
from autism_corpus.utils.http import CachedHttpClient


def _make_pdf(body_text: str, *, title: str | None = None) -> bytes:
    """Build a synthetic 2-page PDF with the given body on page 1 and a stub page 2."""
    doc = pymupdf.open()
    if title is not None:
        doc.set_metadata({"title": title})
    page1 = doc.new_page()
    page1.insert_text((72, 120), body_text, fontsize=12)
    page2 = doc.new_page()
    page2.insert_text(
        (72, 120),
        "Further detail on diagnosis and management of autism in adults.",
        fontsize=12,
    )
    return bytes(doc.tobytes())


class TestNiceGuidelinesAdapterRegistration:
    def test_registered_under_source_id(self) -> None:
        assert adapter_registry()["nice-guidelines"] is NiceGuidelinesAdapter

    def test_class_attributes(self) -> None:
        assert NiceGuidelinesAdapter.source_id == "nice-guidelines"
        assert NiceGuidelinesAdapter.licence == "OGL-UK-3.0"
        assert NiceGuidelinesAdapter.licence_url == (
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        )
        assert NiceGuidelinesAdapter.attribution_template == (
            "From NICE clinical guidelines, licenced under the Open Government Licence v3.0"
        )


class TestNiceGuidelinesAdapterDiscover:
    def test_yields_refs_from_seed_yaml(self, tmp_path: Path) -> None:
        client = CachedHttpClient(source_id="nice-guidelines", cache_dir=tmp_path)
        adapter = NiceGuidelinesAdapter(http_client=client)

        refs = list(adapter.discover())

        item_ids = {r.item_id for r in refs}
        assert "cg128" in item_ids
        assert "cg142" in item_ids
        for ref in refs:
            assert ref.source_id == "nice-guidelines"
            assert ref.url is not None
            assert ref.url.endswith(".pdf")


class TestNiceGuidelinesAdapterFetchAndParse:
    @respx.mock
    def test_fetch_returns_pdf_payload(self, tmp_path: Path) -> None:
        pdf_bytes = _make_pdf(
            "CG128 Autism in adults. Diagnosis and management.",
            title="CG128 Autism in adults",
        )
        respx.get("https://example.test/cg128.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        )
        client = CachedHttpClient(source_id="nice-guidelines", cache_dir=tmp_path)
        adapter = NiceGuidelinesAdapter(http_client=client)
        ref = next(r for r in adapter.discover() if r.item_id == "cg128")

        raw = adapter.fetch(ref)

        assert raw.source_id == "nice-guidelines"
        assert raw.source_item_id == "cg128"
        assert raw.url == "https://example.test/cg128.pdf"
        assert raw.payload == pdf_bytes

    @respx.mock
    def test_parse_produces_clinical_guideline_metadata(self, tmp_path: Path) -> None:
        pdf_bytes = _make_pdf(
            "CG128 Autism in adults. Diagnosis and management.",
            title="CG128 Autism in adults",
        )
        respx.get("https://example.test/cg128.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        )
        client = CachedHttpClient(source_id="nice-guidelines", cache_dir=tmp_path)
        adapter = NiceGuidelinesAdapter(http_client=client)
        ref = next(r for r in adapter.discover() if r.item_id == "cg128")
        raw = adapter.fetch(ref)

        doc = adapter.parse(raw)

        assert doc.source_id == "nice-guidelines"
        assert doc.source_item_id == "cg128"
        assert doc.canonical_url == "https://example.test/cg128.pdf"
        assert doc.licence == "OGL-UK-3.0"
        assert doc.licence_url == (
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        )
        assert doc.attribution == (
            "From NICE clinical guidelines, licenced under the Open Government Licence v3.0"
        )
        assert doc.content_type == "clinical-guideline"
        assert doc.medical_disclaimer_required is True
        assert "CG128" in doc.text or "Autism in adults" in doc.text
        assert len(doc.hash) == 64
