from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.cdc_autism import CdcAutismAdapter
from autism_corpus.config import HttpConfig
from autism_corpus.utils.http import CachedHttpClient

# Sitemap index pointing to two sub-sitemaps; one is autism-related, the other isn't.
_SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://www.cdc.gov/sitemaps/sitemap-autism.xml</loc>
  </sitemap>
  <sitemap>
    <loc>https://www.cdc.gov/sitemaps/sitemap-flu.xml</loc>
  </sitemap>
</sitemapindex>
"""

# Autism sub-sitemap with a mix of autism URLs and non-autism URLs.
_SITEMAP_AUTISM = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.cdc.gov/autism/signs-symptoms/index.html</loc></url>
  <url><loc>https://www.cdc.gov/ncbddd/autism/data.html</loc></url>
  <url><loc>https://www.cdc.gov/flu/about.html</loc></url>
  <url><loc>https://www.cdc.gov/about/index.html</loc></url>
</urlset>
"""

_PAGE_HTML = """<!doctype html>
<html>
<head><title>Signs and Symptoms of Autism</title></head>
<body>
<nav>menu</nav>
<main>
<article>
<h1>Signs and Symptoms of Autism</h1>
<p>Autism spectrum disorder is a developmental disability that affects how
people communicate, learn, and behave. The signs often appear in early
childhood and can vary widely from person to person.</p>
<p>Some children show signs by 12 months of age while others may not show
signs until 24 months or later.</p>
</article>
</main>
<footer>copyright</footer>
</body>
</html>
"""


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def http_config() -> HttpConfig:
    return HttpConfig(per_host_rate_per_second=100.0, max_retries=0)


class TestCdcAutismAdapterRegistration:
    def test_adapter_is_registered_under_source_id(self) -> None:
        assert adapter_registry()["cdc-autism"] is CdcAutismAdapter

    def test_class_attributes(self) -> None:
        assert CdcAutismAdapter.source_id == "cdc-autism"
        assert CdcAutismAdapter.licence == "public-domain"
        assert CdcAutismAdapter.licence_url == "https://www.cdc.gov/other/agencymaterials.html"
        assert (
            CdcAutismAdapter.attribution_template
            == "U.S. Centers for Disease Control and Prevention (public domain)"
        )


class TestCdcAutismDiscover:
    @respx.mock
    def test_discover_filters_to_autism_urls(
        self, cache_dir: Path, http_config: HttpConfig
    ) -> None:
        respx.get("https://www.cdc.gov/sitemap.xml").mock(
            return_value=httpx.Response(
                200, text=_SITEMAP_INDEX, headers={"content-type": "application/xml"}
            )
        )
        respx.get("https://www.cdc.gov/sitemaps/sitemap-autism.xml").mock(
            return_value=httpx.Response(
                200, text=_SITEMAP_AUTISM, headers={"content-type": "application/xml"}
            )
        )
        client = CachedHttpClient(
            source_id="cdc-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcAutismAdapter(http_client=client)
        urls = [ref.url for ref in adapter.discover()]
        assert "https://www.cdc.gov/autism/signs-symptoms/index.html" in urls
        assert "https://www.cdc.gov/ncbddd/autism/data.html" in urls
        assert "https://www.cdc.gov/flu/about.html" not in urls
        assert "https://www.cdc.gov/about/index.html" not in urls

    @respx.mock
    def test_discover_yields_source_item_refs_with_source_id(
        self, cache_dir: Path, http_config: HttpConfig
    ) -> None:
        respx.get("https://www.cdc.gov/sitemap.xml").mock(
            return_value=httpx.Response(200, text=_SITEMAP_INDEX)
        )
        respx.get("https://www.cdc.gov/sitemaps/sitemap-autism.xml").mock(
            return_value=httpx.Response(200, text=_SITEMAP_AUTISM)
        )
        client = CachedHttpClient(
            source_id="cdc-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcAutismAdapter(http_client=client)
        refs = list(adapter.discover())
        assert all(ref.source_id == "cdc-autism" for ref in refs)
        assert all(ref.item_id for ref in refs)

    @respx.mock
    def test_discover_falls_back_to_scanning_all_subsitemaps(
        self, cache_dir: Path, http_config: HttpConfig
    ) -> None:
        # Sitemap index with no obviously autism-named sub-sitemap.
        index = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.cdc.gov/sitemaps/sitemap-misc.xml</loc></sitemap>
</sitemapindex>
"""
        misc_urlset = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.cdc.gov/autism/about.html</loc></url>
  <url><loc>https://www.cdc.gov/flu/index.html</loc></url>
</urlset>
"""
        respx.get("https://www.cdc.gov/sitemap.xml").mock(
            return_value=httpx.Response(200, text=index)
        )
        respx.get("https://www.cdc.gov/sitemaps/sitemap-misc.xml").mock(
            return_value=httpx.Response(200, text=misc_urlset)
        )
        client = CachedHttpClient(
            source_id="cdc-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcAutismAdapter(http_client=client)
        urls = [ref.url for ref in adapter.discover()]
        assert "https://www.cdc.gov/autism/about.html" in urls
        assert "https://www.cdc.gov/flu/index.html" not in urls

    @respx.mock
    def test_discover_accepts_sitemap_url_override(
        self, cache_dir: Path, http_config: HttpConfig
    ) -> None:
        # A different sitemap-index URL should be used when explicitly passed.
        custom_index = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.test/sub.xml</loc></sitemap>
</sitemapindex>
"""
        sub_urlset = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.test/autism/page.html</loc></url>
</urlset>
"""
        respx.get("https://example.test/index.xml").mock(
            return_value=httpx.Response(200, text=custom_index)
        )
        respx.get("https://example.test/sub.xml").mock(
            return_value=httpx.Response(200, text=sub_urlset)
        )
        client = CachedHttpClient(
            source_id="cdc-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcAutismAdapter(
            http_client=client, sitemap_url="https://example.test/index.xml"
        )
        urls = [ref.url for ref in adapter.discover()]
        assert urls == ["https://example.test/autism/page.html"]


class TestCdcAutismFetchAndParse:
    @respx.mock
    def test_end_to_end_discover_fetch_parse(
        self, cache_dir: Path, http_config: HttpConfig
    ) -> None:
        respx.get("https://www.cdc.gov/sitemap.xml").mock(
            return_value=httpx.Response(200, text=_SITEMAP_INDEX)
        )
        respx.get("https://www.cdc.gov/sitemaps/sitemap-autism.xml").mock(
            return_value=httpx.Response(200, text=_SITEMAP_AUTISM)
        )
        respx.get("https://www.cdc.gov/autism/signs-symptoms/index.html").mock(
            return_value=httpx.Response(
                200, text=_PAGE_HTML, headers={"content-type": "text/html"}
            )
        )
        client = CachedHttpClient(
            source_id="cdc-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = CdcAutismAdapter(http_client=client)
        refs = [
            r
            for r in adapter.discover()
            if r.url == "https://www.cdc.gov/autism/signs-symptoms/index.html"
        ]
        assert len(refs) == 1
        raw = adapter.fetch(refs[0])
        doc = adapter.parse(raw)

        assert doc.source_id == "cdc-autism"
        assert doc.licence == "public-domain"
        assert doc.licence_url == "https://www.cdc.gov/other/agencymaterials.html"
        assert (
            doc.attribution
            == "U.S. Centers for Disease Control and Prevention (public domain)"
        )
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert doc.canonical_url == raw.url
        assert "Signs and Symptoms of Autism" in doc.title
        assert "Autism spectrum disorder" in doc.text
