from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.nih_nimh import NihNimhAdapter
from autism_corpus.config import HttpConfig
from autism_corpus.utils.http import CachedHttpClient

_PAGE_HTML = """<!doctype html>
<html>
<head><title>Autism Spectrum Disorder</title></head>
<body>
<nav>menu</nav>
<main>
<article>
<h1>Autism Spectrum Disorder</h1>
<p>Autism spectrum disorder (ASD) is a developmental disorder that affects
communication and behavior. Although autism can be diagnosed at any age,
it is described as a developmental disorder because symptoms generally
appear in the first two years of life.</p>
</article>
</main>
</body>
</html>
"""

_SEED_YAML = """\
nih-nimh:
  - item_id: autism-spectrum-disorder
    url: https://example.test/nimh/asd.html
  - item_id: autism-statistics
    url: https://example.test/nimh/stats.html
"""


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


class TestNihNimhAdapterRegistration:
    def test_adapter_is_registered_under_source_id(self) -> None:
        assert adapter_registry()["nih-nimh"] is NihNimhAdapter

    def test_class_attributes(self) -> None:
        assert NihNimhAdapter.source_id == "nih-nimh"
        assert NihNimhAdapter.licence == "public-domain"
        assert NihNimhAdapter.licence_url == "https://www.nimh.nih.gov/site-info/policies"
        assert (
            NihNimhAdapter.attribution_template
            == "National Institute of Mental Health, NIH (public domain)"
        )


class TestNihNimhDiscover:
    def test_discover_reads_seed_yaml(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        client = CachedHttpClient(
            source_id="nih-nimh", cache_dir=cache_dir, config=http_config
        )
        adapter = NihNimhAdapter(http_client=client, seed_path=seed_path)
        refs = list(adapter.discover())
        assert {ref.item_id for ref in refs} == {
            "autism-spectrum-disorder",
            "autism-statistics",
        }
        assert all(ref.source_id == "nih-nimh" for ref in refs)
        assert all(ref.url and ref.url.startswith("https://") for ref in refs)


class TestNihNimhFetchAndParse:
    @respx.mock
    def test_end_to_end_round_trip(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        respx.get("https://example.test/nimh/asd.html").mock(
            return_value=httpx.Response(
                200, text=_PAGE_HTML, headers={"content-type": "text/html"}
            )
        )
        client = CachedHttpClient(
            source_id="nih-nimh", cache_dir=cache_dir, config=http_config
        )
        adapter = NihNimhAdapter(http_client=client, seed_path=seed_path)
        ref = next(
            r for r in adapter.discover() if r.item_id == "autism-spectrum-disorder"
        )
        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "nih-nimh"
        assert doc.licence == "public-domain"
        assert doc.licence_url == "https://www.nimh.nih.gov/site-info/policies"
        assert (
            doc.attribution
            == "National Institute of Mental Health, NIH (public domain)"
        )
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert doc.canonical_url == raw.url
        assert "Autism Spectrum Disorder" in doc.title
        assert "developmental disorder" in doc.text.lower()
