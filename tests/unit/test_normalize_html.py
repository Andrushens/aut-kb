from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from autism_corpus.normalize.html import HtmlExtraction, extract_html

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "html" / "sample_cdc.html"


@pytest.fixture
def sample_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def extraction(sample_html: str) -> HtmlExtraction:
    return extract_html(sample_html, url="https://www.cdc.gov/autism/signs-symptoms/")


class TestExtractHtml:
    def test_returns_html_extraction(self, extraction: HtmlExtraction) -> None:
        assert isinstance(extraction, HtmlExtraction)

    def test_title_extracted(self, extraction: HtmlExtraction) -> None:
        assert "Signs and Symptoms of Autism Spectrum Disorder" in extraction.title

    def test_nav_links_stripped(self, extraction: HtmlExtraction) -> None:
        assert "About CDC" not in extraction.text
        assert "Contact Us" not in extraction.text

    def test_footer_stripped(self, extraction: HtmlExtraction) -> None:
        assert "1600 Clifton Rd" not in extraction.text
        assert "Accessibility" not in extraction.text

    def test_cookie_banner_stripped(self, extraction: HtmlExtraction) -> None:
        assert "Accept all cookies" not in extraction.text
        assert "Manage preferences" not in extraction.text

    def test_share_widget_stripped(self, extraction: HtmlExtraction) -> None:
        assert "Share on Facebook" not in extraction.text
        assert "Share on Twitter" not in extraction.text

    def test_main_content_present(self, extraction: HtmlExtraction) -> None:
        assert "developmental disability" in extraction.text
        assert "echolalia" in extraction.text

    def test_h1_rendered_as_markdown(self, extraction: HtmlExtraction) -> None:
        assert "# Signs and Symptoms of Autism Spectrum Disorder" in extraction.text

    def test_h2_rendered_as_markdown(self, extraction: HtmlExtraction) -> None:
        assert "## Social Communication and Interaction Skills" in extraction.text
        assert "## Development" in extraction.text

    def test_h3_rendered_as_markdown(self, extraction: HtmlExtraction) -> None:
        assert "### Restricted or Repetitive Behaviors or Interests" in extraction.text

    def test_list_items_rendered_as_markdown(self, extraction: HtmlExtraction) -> None:
        assert "- Avoiding or not keeping eye contact" in extraction.text
        assert "- Repeating words or phrases over and over (echolalia)" in extraction.text

    def test_figures_captured_in_document_order(self, extraction: HtmlExtraction) -> None:
        assert extraction.figures == ["diagram of brain"]

    def test_no_img_tag_in_text(self, extraction: HtmlExtraction) -> None:
        assert "<img" not in extraction.text

    def test_no_raw_html_tags_in_text(self, extraction: HtmlExtraction) -> None:
        # Common tags that must never leak into rendered text.
        for tag in ("<p>", "</p>", "<ul>", "</ul>", "<li>", "</li>", "<h1>", "<h2>"):
            assert tag not in extraction.text

    def test_last_modified_parsed_from_meta(self, extraction: HtmlExtraction) -> None:
        assert extraction.last_modified == date(2024, 3, 15)


class TestExtractHtmlNoMeta:
    def test_last_modified_is_none_when_missing(self) -> None:
        html = (
            "<!DOCTYPE html><html><head><title>X</title></head>"
            "<body><main><article><h1>X</h1><p>"
            "Autism is a developmental condition that affects many children."
            "</p></article></main></body></html>"
        )
        result = extract_html(html)
        assert result.last_modified is None

    def test_figures_empty_when_no_images(self) -> None:
        html = (
            "<!DOCTYPE html><html><head><title>Y</title></head>"
            "<body><main><article><h1>Y</h1><p>"
            "Autism is a developmental condition that affects many children."
            "</p></article></main></body></html>"
        )
        result = extract_html(html)
        assert result.figures == []
