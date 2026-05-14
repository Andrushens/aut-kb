from __future__ import annotations

from pathlib import Path

import httpx
import pymupdf
import pytest
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.cdc_ltsae import CdcLtsaeAdapter
from autism_corpus.config import HttpConfig
from autism_corpus.utils.http import CachedHttpClient

_HTML_PAGE = """<!doctype html>
<html>
<head><title>Milestones Overview</title></head>
<body>
<nav>menu</nav>
<main>
<article>
<h1>Developmental Milestones</h1>
<p>Track your child's developmental milestones from age 2 months to 5 years.
Look at the milestones your child has reached by the end of each age range.</p>
<p>Acting early can make a real difference for children with developmental delay.</p>
</article>
</main>
</body>
</html>
"""

_SEED_YAML = """\
cdc-ltsae:
  - item_id: milestones-overview
    url: https://example.test/cdc/ltsae/milestones.html
    kind: html
  - item_id: milestones-checklist-2y
    url: https://example.test/cdc/ltsae/checklist-2y.pdf
    kind: pdf
"""


def _build_pdf_bytes() -> bytes:
    doc = pymupdf.open()
    doc.set_metadata({"title": "Milestones Checklist 2 Years"})
    page = doc.new_page()
    page.insert_text(
        (72, 120),
        "By age 2 years your child should be able to walk and follow simple instructions.",
        fontsize=12,
    )
    return bytes(doc.tobytes())


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def http_config() -> HttpConfig:
    return HttpConfig(per_host_rate_per_second=100.0, max_retries=0)


@pytest.fixture
def seed_path(tmp_path: Path) -> Path:
    path = tmp_path / "seed_urls.yaml"
    path.write_text(_SEED_YAML)
    return path


class TestCdcLtsaeAdapterRegistration:
    def test_adapter_is_registered_under_source_id(self) -> None:
        assert adapter_registry()["cdc-ltsae"] is CdcLtsaeAdapter

    def test_class_attributes(self) -> None:
        assert CdcLtsaeAdapter.source_id == "cdc-ltsae"
        assert CdcLtsaeAdapter.licence == "public-domain"
        assert CdcLtsaeAdapter.licence_url == "https://www.cdc.gov/other/agencymaterials.html"
        assert (
            CdcLtsaeAdapter.attribution_template
            == "U.S. Centers for Disease Control and Prevention (public domain)"
        )


class TestCdcLtsaeDiscover:
    def test_discover_reads_seed_yaml(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        client = CachedHttpClient(
            source_id="cdc-ltsae", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcLtsaeAdapter(http_client=client, seed_path=seed_path)
        refs = list(adapter.discover())
        assert len(refs) == 2
        item_ids = {ref.item_id for ref in refs}
        assert item_ids == {"milestones-overview", "milestones-checklist-2y"}
        assert all(ref.source_id == "cdc-ltsae" for ref in refs)


class TestCdcLtsaeFetchAndParseHtml:
    @respx.mock
    def test_html_seed_round_trip(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        respx.get("https://example.test/cdc/ltsae/milestones.html").mock(
            return_value=httpx.Response(
                200, text=_HTML_PAGE, headers={"content-type": "text/html"}
            )
        )
        client = CachedHttpClient(
            source_id="cdc-ltsae", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcLtsaeAdapter(http_client=client, seed_path=seed_path)
        ref = next(r for r in adapter.discover() if r.item_id == "milestones-overview")
        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "cdc-ltsae"
        assert doc.licence == "public-domain"
        assert doc.licence_url == "https://www.cdc.gov/other/agencymaterials.html"
        assert (
            doc.attribution
            == "U.S. Centers for Disease Control and Prevention (public domain)"
        )
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert doc.canonical_url == raw.url
        assert "Developmental Milestones" in doc.title
        assert "developmental milestones" in doc.text.lower()


class TestCdcLtsaeFetchAndParsePdf:
    @respx.mock
    def test_pdf_seed_round_trip(
        self,
        cache_dir: Path,
        http_config: HttpConfig,
        seed_path: Path,
    ) -> None:
        pdf_bytes = _build_pdf_bytes()
        respx.get("https://example.test/cdc/ltsae/checklist-2y.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        )
        client = CachedHttpClient(
            source_id="cdc-ltsae", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcLtsaeAdapter(http_client=client, seed_path=seed_path)
        ref = next(
            r for r in adapter.discover() if r.item_id == "milestones-checklist-2y"
        )
        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "cdc-ltsae"
        assert doc.licence == "public-domain"
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert doc.canonical_url == raw.url
        # PDF text should have been extracted.
        assert "age 2 years" in doc.text.lower()
