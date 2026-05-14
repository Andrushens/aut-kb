"""End-to-end smoke test of `autism-corpus build` against mocked HTTP.

Wires real registered adapters (nhs-autism, cdc-autism, nih-nimh,
medlineplus-autism, who-autism) through to chunks.jsonl with respx-mocked
HTTP responses for the few URLs each adapter touches. PMC is excluded because
it requires injected loaders the CLI doesn't supply.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from autism_corpus import cli as cli_module
from autism_corpus.adapters import nice_guidelines as nice_module
from autism_corpus.adapters import who as who_module
from autism_corpus.adapters.base import adapter_registry
from autism_corpus.cli import app
from autism_corpus.utils.http import CachedHttpClient

_NHS_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.nhs.uk/conditions/autism/signs/children/</loc></url>
  <url><loc>https://www.nhs.uk/conditions/some-other-condition/</loc></url>
</urlset>
"""

_NHS_FILLER = (
    " Autistic children may show differences in communication, social "
    "interaction, and sensory processing." * 30
)
_NHS_PAGE = (
    "<!doctype html><html><head>"
    "<title>Signs of autism in children</title>"
    '<meta name="last-modified" content="2024-03-01">'
    "</head><body><nav>menu</nav><main>"
    "<h1>Signs of autism in children</h1>"
    "<p>This page describes signs of autism that parents and teachers may "
    "observe in young children. The behaviours listed here are common "
    "indicators worth discussing with a clinician for a full assessment."
    + _NHS_FILLER
    + "</p><h2>What to do next</h2>"
    "<p>Speak to your GP or health visitor if you have concerns about a "
    "child's development. They can refer you for a formal assessment.</p>"
    "</main><footer>copyright</footer></body></html>"
)

_CDC_SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.cdc.gov/autism-sitemap.xml</loc></sitemap>
</sitemapindex>
"""

_CDC_SUB_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.cdc.gov/autism/about/index.html</loc></url>
  <url><loc>https://www.cdc.gov/flu/about/index.html</loc></url>
</urlset>
"""

_CDC_FILLER = (
    " Autism spectrum disorder describes differences in social "
    "communication, sensory processing, and repetitive interests; "
    "clinicians use validated screening tools." * 80
)
_CDC_PAGE = (
    "<!doctype html><html><head><title>About autism</title></head>"
    "<body><main>"
    "<h1>About autism</h1>"
    "<p>Autism spectrum disorder is a developmental condition that affects "
    "how people communicate, interact, and experience the world. It is "
    "diagnosed by clinicians using standardised criteria."
    + _CDC_FILLER
    + "</p></main></body></html>"
)

def _vary(label: str) -> str:
    body = "<!doctype html><html><head><title>About autism</title></head><body><main>"
    body += f"<h1>About autism — {label}</h1><p>"
    body += (
        f"The {label} resource summarises autism spectrum disorder for general "
        "audiences. " * 60
    )
    body += "</p></main></body></html>"
    return body


_NIMH_PAGE = _vary("NIMH")
_MEDLINEPLUS_PAGE = _vary("MedlinePlus")
_WHO_PAGE = _vary("WHO")


@pytest.fixture
def seed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write an integration-test seed file and point all seed-driven adapters
    at it, so we don't depend on the production data/seed_urls.yaml content.
    """
    seed = {
        "nice-guidelines": [],
        "who-autism": [
            {
                "item_id": "autism-fact-sheet",
                "url": "https://example.test/who/autism.html",
                "kind": "html",
            }
        ],
        "cdc-ltsae": [],
        "nih-nimh": [
            {
                "item_id": "asd",
                "url": "https://example.test/nimh/asd.html",
            }
        ],
        "medlineplus-autism": [
            {
                "item_id": "asd",
                "url": "https://example.test/medlineplus/asd.html",
            }
        ],
    }
    seed_path = tmp_path / "seed_urls.yaml"
    seed_path.write_text(yaml.safe_dump(seed))
    # WHO + NICE read seeds from a module-level constant; redirect it to our
    # test seed file for the duration of the test.
    monkeypatch.setattr(who_module, "_SEED_FILE", seed_path, raising=False)
    monkeypatch.setattr(nice_module, "_SEED_FILE", seed_path, raising=False)

    def _patched(settings, *, cache_root, only=None):  # type: ignore[no-untyped-def]
        cli_module._import_adapters()
        only_set: set[str] | None = set(only) if only else None
        adapters = []
        seed_kwarg_sources = {"cdc-ltsae", "nih-nimh", "medlineplus-autism"}
        for sid, cls in adapter_registry().items():
            if only_set is not None and sid not in only_set:
                continue
            if sid == "pmc-oa-autism":
                continue
            client = CachedHttpClient(
                source_id=sid, cache_dir=cache_root, config=settings.http
            )
            kwargs: dict[str, object] = {}
            if sid in seed_kwarg_sources:
                kwargs["seed_path"] = seed_path
            adapters.append(cls(client, **kwargs))
        return adapters

    monkeypatch.setattr(cli_module, "_build_registered_adapters", _patched)
    return seed_path


@respx.mock
def test_build_end_to_end_produces_artifacts(
    seed_file: Path, tmp_path: Path
) -> None:
    respx.get("https://www.nhs.uk/sitemap.xml").mock(
        return_value=httpx.Response(200, text=_NHS_SITEMAP)
    )
    respx.get("https://www.nhs.uk/conditions/autism/signs/children/").mock(
        return_value=httpx.Response(200, text=_NHS_PAGE)
    )
    respx.get("https://www.cdc.gov/sitemap.xml").mock(
        return_value=httpx.Response(200, text=_CDC_SITEMAP_INDEX)
    )
    respx.get("https://www.cdc.gov/autism-sitemap.xml").mock(
        return_value=httpx.Response(200, text=_CDC_SUB_SITEMAP)
    )
    respx.get("https://www.cdc.gov/autism/about/index.html").mock(
        return_value=httpx.Response(200, text=_CDC_PAGE)
    )
    respx.get("https://example.test/who/autism.html").mock(
        return_value=httpx.Response(200, text=_WHO_PAGE)
    )
    respx.get("https://example.test/nimh/asd.html").mock(
        return_value=httpx.Response(200, text=_NIMH_PAGE)
    )
    respx.get("https://example.test/medlineplus/asd.html").mock(
        return_value=httpx.Response(200, text=_MEDLINEPLUS_PAGE)
    )

    runner = CliRunner()
    out_root = tmp_path / "output"
    cache_root = tmp_path / "cache"
    result = runner.invoke(
        app,
        [
            "build",
            "--only",
            "nhs-autism",
            "--only",
            "cdc-autism",
            "--only",
            "nih-nimh",
            "--only",
            "medlineplus-autism",
            "--only",
            "who-autism",
            "--run-id",
            "integration",
            "--output-root",
            str(out_root),
            "--cache-root",
            str(cache_root),
        ],
    )
    assert result.exit_code == 0, result.stdout

    run_dir = out_root / "integration"
    documents_path = run_dir / "documents.jsonl"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "report.html"

    assert documents_path.exists() and chunks_path.exists()
    assert manifest_path.exists() and report_path.exists()

    docs = [json.loads(line) for line in documents_path.read_text().splitlines() if line]
    chunks = [json.loads(line) for line in chunks_path.read_text().splitlines() if line]
    manifest = json.loads(manifest_path.read_text())

    # Five sources each yield one document.
    source_ids = {d["source_id"] for d in docs}
    assert source_ids == {
        "nhs-autism",
        "cdc-autism",
        "nih-nimh",
        "medlineplus-autism",
        "who-autism",
    }
    assert len(chunks) >= len(docs)

    # Every chunk has full provenance.
    for chunk in chunks:
        assert chunk["licence"], chunk
        assert chunk["attribution"]
        assert chunk["canonical_url"].startswith("http")
        assert chunk["breadcrumb"]
        assert chunk["token_count"] > 0

    # Manifest licences are recognised.
    known = {
        "public-domain",
        "OGL-UK-3.0",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC-BY-ND-4.0",
        "CC0-1.0",
        "CC-BY-NC-SA-3.0-IGO",
    }
    assert set(manifest["licences"].keys()).issubset(known), manifest["licences"]

    # Report mentions all five sources.
    report_body = report_path.read_text()
    for sid in source_ids:
        assert sid in report_body
