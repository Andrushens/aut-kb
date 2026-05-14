from __future__ import annotations

from pathlib import Path

import httpx
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.nhs_autism import NhsAutismAdapter
from autism_corpus.utils.http import CachedHttpClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nhs"


def _sitemap_bytes() -> bytes:
    return (FIXTURES / "sitemap.xml").read_bytes()


def _signs_children_html() -> bytes:
    return (FIXTURES / "signs_children.html").read_bytes()


class TestNhsAutismAdapterRegistration:
    def test_registered_under_source_id(self) -> None:
        assert adapter_registry()["nhs-autism"] is NhsAutismAdapter

    def test_class_attributes(self) -> None:
        assert NhsAutismAdapter.source_id == "nhs-autism"
        assert NhsAutismAdapter.licence == "OGL-UK-3.0"
        assert NhsAutismAdapter.licence_url == (
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        )
        assert NhsAutismAdapter.attribution_template == (
            "Information from NHS Digital, licenced under the Open Government Licence v3.0"
        )


class TestNhsAutismAdapterDiscover:
    @respx.mock
    def test_yields_only_autism_urls(self, tmp_path: Path) -> None:
        respx.get("https://www.nhs.uk/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=_sitemap_bytes(),
                headers={"content-type": "application/xml"},
            )
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        adapter = NhsAutismAdapter(http_client=client)

        refs = list(adapter.discover())

        urls = [r.url for r in refs]
        # All three autism URLs included
        assert "https://www.nhs.uk/conditions/autism/signs/children" in urls
        assert "https://www.nhs.uk/conditions/autism/signs/adults" in urls
        assert "https://www.nhs.uk/conditions/autism/getting-diagnosed" in urls
        # Non-autism URLs filtered out
        assert "https://www.nhs.uk/conditions/flu" not in urls
        assert "https://www.nhs.uk/medicines/paracetamol" not in urls
        assert len(refs) == 3

    @respx.mock
    def test_ref_item_id_is_url_path_without_leading_slash(self, tmp_path: Path) -> None:
        respx.get("https://www.nhs.uk/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=_sitemap_bytes(),
                headers={"content-type": "application/xml"},
            )
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        adapter = NhsAutismAdapter(http_client=client)

        refs = list(adapter.discover())

        item_ids = {r.item_id for r in refs}
        assert "conditions/autism/signs/children" in item_ids
        assert "conditions/autism/signs/adults" in item_ids
        assert "conditions/autism/getting-diagnosed" in item_ids

    @respx.mock
    def test_ref_source_id_is_nhs_autism(self, tmp_path: Path) -> None:
        respx.get("https://www.nhs.uk/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=_sitemap_bytes(),
                headers={"content-type": "application/xml"},
            )
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        adapter = NhsAutismAdapter(http_client=client)

        for ref in adapter.discover():
            assert ref.source_id == "nhs-autism"


class TestNhsAutismAdapterFetchAndParse:
    @respx.mock
    def test_fetch_returns_raw_document(self, tmp_path: Path) -> None:
        respx.get("https://www.nhs.uk/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=_sitemap_bytes(),
                headers={"content-type": "application/xml"},
            )
        )
        respx.get("https://www.nhs.uk/conditions/autism/signs/children").mock(
            return_value=httpx.Response(
                200,
                content=_signs_children_html(),
                headers={"content-type": "text/html"},
            )
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        adapter = NhsAutismAdapter(http_client=client)
        refs = list(adapter.discover())
        target = next(
            r for r in refs if r.url == "https://www.nhs.uk/conditions/autism/signs/children"
        )

        raw = adapter.fetch(target)

        assert raw.source_id == "nhs-autism"
        assert raw.source_item_id == "conditions/autism/signs/children"
        assert raw.url == "https://www.nhs.uk/conditions/autism/signs/children"
        assert b"Signs of autism in children" in raw.payload

    @respx.mock
    def test_parse_produces_correct_metadata(self, tmp_path: Path) -> None:
        respx.get("https://www.nhs.uk/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=_sitemap_bytes(),
                headers={"content-type": "application/xml"},
            )
        )
        respx.get("https://www.nhs.uk/conditions/autism/signs/children").mock(
            return_value=httpx.Response(
                200,
                content=_signs_children_html(),
                headers={"content-type": "text/html"},
            )
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=tmp_path)
        adapter = NhsAutismAdapter(http_client=client)
        ref = next(
            r
            for r in adapter.discover()
            if r.url == "https://www.nhs.uk/conditions/autism/signs/children"
        )
        raw = adapter.fetch(ref)

        doc = adapter.parse(raw)

        assert doc.source_id == "nhs-autism"
        assert doc.source_item_id == "conditions/autism/signs/children"
        assert doc.canonical_url == "https://www.nhs.uk/conditions/autism/signs/children"
        assert doc.licence == "OGL-UK-3.0"
        assert doc.licence_url == (
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        )
        assert doc.attribution == (
            "Information from NHS Digital, licenced under the Open Government Licence v3.0"
        )
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert "Signs of autism in children" in doc.title
        assert "autism" in doc.text.lower()
        assert len(doc.hash) == 64
