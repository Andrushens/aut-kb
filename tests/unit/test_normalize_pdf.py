from __future__ import annotations

import pymupdf
import pytest

from autism_corpus.normalize.pdf import PdfExtraction, extract_pdf


def _make_pdf(
    pages: list[str],
    *,
    title: str | None = None,
    header: str | None = None,
    footer: str | None = None,
) -> bytes:
    """Build a synthetic PDF with optional repeated header/footer per page."""
    doc = pymupdf.open()
    if title is not None:
        doc.set_metadata({"title": title})
    for body in pages:
        page = doc.new_page()
        if header is not None:
            page.insert_text((72, 36), header, fontsize=10)
        page.insert_text((72, 120), body, fontsize=12)
        if footer is not None:
            # near bottom of A4 page (~842pt tall)
            page.insert_text((72, 800), footer, fontsize=10)
    return bytes(doc.tobytes())


@pytest.fixture
def two_page_pdf() -> bytes:
    return _make_pdf(
        [
            "First page content discussing autism diagnosis.",
            "Second page content discussing autism support.",
        ],
        title="Autism Toolkit",
    )


class TestExtractPdfBasic:
    def test_returns_pdf_extraction(self, two_page_pdf: bytes) -> None:
        result = extract_pdf(two_page_pdf)
        assert isinstance(result, PdfExtraction)

    def test_page_count(self, two_page_pdf: bytes) -> None:
        result = extract_pdf(two_page_pdf)
        assert result.page_count == 2

    def test_text_from_both_pages_present(self, two_page_pdf: bytes) -> None:
        result = extract_pdf(two_page_pdf)
        assert "First page content discussing autism diagnosis." in result.text
        assert "Second page content discussing autism support." in result.text

    def test_page_separator_is_double_newline(self, two_page_pdf: bytes) -> None:
        result = extract_pdf(two_page_pdf)
        # Exactly one "\n\n" between the two pages and no form-feed characters.
        assert "\f" not in result.text
        assert "First page content discussing autism diagnosis." in result.text
        assert "\n\nSecond page content" in result.text

    def test_title_from_metadata(self, two_page_pdf: bytes) -> None:
        result = extract_pdf(two_page_pdf)
        assert result.title == "Autism Toolkit"


class TestExtractPdfTitleMissing:
    def test_title_is_none_when_metadata_missing(self) -> None:
        pdf = _make_pdf(["Just some text on a single page."])
        result = extract_pdf(pdf)
        assert result.title is None


class TestExtractPdfHeaderFooterStripping:
    def test_repeating_header_and_footer_removed(self) -> None:
        pdf = _make_pdf(
            [
                "Body of page one with unique content here.",
                "Body of page two with different unique content.",
                "Body of page three with yet more unique content.",
            ],
            header="Confidential Draft Header",
            footer="Page X of Y",
        )
        result = extract_pdf(pdf)
        assert "Confidential Draft Header" not in result.text
        assert "Page X of Y" not in result.text
        # Unique body content survives.
        assert "Body of page one" in result.text
        assert "Body of page two" in result.text
        assert "Body of page three" in result.text
