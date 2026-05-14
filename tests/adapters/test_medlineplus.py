from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from autism_corpus.adapters.base import adapter_registry
from autism_corpus.adapters.medlineplus import MedlinePlusAdapter
from autism_corpus.config import HttpConfig
from autism_corpus.utils.http import CachedHttpClient

_PAGE_HTML = """<!doctype html>
<html>
<head><title>Autism Spectrum Disorder - MedlinePlus</title></head>
<body>
<nav>menu</nav>
<main>
<article>
<h1>Autism Spectrum Disorder</h1>
<p>Autism spectrum disorder (ASD) is a neurological and developmental
disorder that affects how people interact with others, communicate, learn,
and behave. ASD can be diagnosed at any age but it is described as a
developmental disorder because symptoms generally appear in the first two
years of life.</p>
</article>
</main>
</body>
</html>
"""

_SEED_YAML = """\
medlineplus-autism:
  - item_id: autism-spectrum-disorder
    url: https://example.test/medlineplus/asd.html
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


class TestMedlinePlusAdapterRegistration:
    def test_adapter_is_registered_under_source_id(self) -> None:
        assert adapter_registry()["medlineplus-autism"] is MedlinePlusAdapter

    def test_class_attributes(self) -> None:
        assert MedlinePlusAdapter.source_id == "medlineplus-autism"
        assert MedlinePlusAdapter.licence == "public-domain"
        assert (
            MedlinePlusAdapter.licence_url
            == "https://medlineplus.gov/about/using/usingcontent/"
        )
        assert (
            MedlinePlusAdapter.attribution_template
            == "MedlinePlus, U.S. National Library of Medicine (public domain)"
        )


class TestMedlinePlusDiscover:
    def test_discover_reads_seed_yaml(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        client = CachedHttpClient(
            source_id="medlineplus-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = MedlinePlusAdapter(http_client=client, seed_path=seed_path)
        refs = list(adapter.discover())
        assert [ref.item_id for ref in refs] == ["autism-spectrum-disorder"]
        assert refs[0].source_id == "medlineplus-autism"


class TestMedlinePlusFetchAndParse:
    @respx.mock
    def test_end_to_end_round_trip(
        self, cache_dir: Path, http_config: HttpConfig, seed_path: Path
    ) -> None:
        respx.get("https://example.test/medlineplus/asd.html").mock(
            return_value=httpx.Response(
                200, text=_PAGE_HTML, headers={"content-type": "text/html"}
            )
        )
        client = CachedHttpClient(
            source_id="medlineplus-autism", cache_dir=cache_dir, config=http_config
        )
        adapter = MedlinePlusAdapter(http_client=client, seed_path=seed_path)
        ref = next(iter(adapter.discover()))
        raw = adapter.fetch(ref)
        doc = adapter.parse(raw)

        assert doc.source_id == "medlineplus-autism"
        assert doc.licence == "public-domain"
        assert (
            doc.licence_url == "https://medlineplus.gov/about/using/usingcontent/"
        )
        assert (
            doc.attribution
            == "MedlinePlus, U.S. National Library of Medicine (public domain)"
        )
        assert doc.content_type == "patient-info"
        assert doc.medical_disclaimer_required is False
        assert doc.canonical_url == raw.url
        assert "Autism Spectrum Disorder" in doc.title
        assert "developmental disorder" in doc.text.lower()
