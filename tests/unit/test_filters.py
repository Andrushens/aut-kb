from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from autism_corpus.filters import FilterConfig, apply_filters
from autism_corpus.models import ContentType, ParsedDocument


def _doc(
    *,
    source_item_id: str = "x",
    canonical_url: str = "https://example.com/article",
    text: str = "Body text.",
    last_modified_at: date | None = date(2024, 1, 1),
    content_type: ContentType = "patient-info",
    hash_seed: str = "a",
) -> ParsedDocument:
    kwargs: dict[str, Any] = {
        "source_id": "nhs-autism",
        "source_item_id": source_item_id,
        "canonical_url": canonical_url,
        "title": "Title",
        "text": text,
        "language": "en",
        "published_at": date(2023, 1, 1),
        "last_modified_at": last_modified_at,
        "licence": "OGL-UK-3.0",
        "licence_url": "https://example.com/licence",
        "attribution": "Attribution",
        "content_type": content_type,
        "medical_disclaimer_required": False,
        "hash": hash_seed * 64,
        "fetched_at": datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
    }
    return ParsedDocument(**kwargs)


@pytest.fixture
def empty_excluded_urls(tmp_path: Path) -> Path:
    p = tmp_path / "excluded_urls.yaml"
    p.write_text("urls: []\n")
    return p


def _long_text(n_words: int) -> str:
    # Each space-separated word is ~1 token under cl100k_base.
    return " ".join(["autism"] * n_words)


class TestApplyFilters:
    def test_old_patient_info_dropped(self, empty_excluded_urls: Path) -> None:
        old_doc = _doc(
            source_item_id="old",
            last_modified_at=date(2014, 5, 14),
            text=_long_text(500),
        )
        cfg = FilterConfig(
            today=date(2026, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([old_doc], cfg)
        assert report.kept == []
        assert len(report.dropped) == 1
        dropped_doc, reason = report.dropped[0]
        assert dropped_doc == old_doc
        assert reason == "too_old"

    def test_old_clinical_guideline_kept(self, empty_excluded_urls: Path) -> None:
        old_guideline = _doc(
            source_item_id="guideline",
            last_modified_at=date(2014, 5, 14),
            content_type="clinical-guideline",
            text=_long_text(500),
        )
        cfg = FilterConfig(
            today=date(2026, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([old_guideline], cfg)
        assert report.kept == [old_guideline]
        assert report.dropped == []

    def test_too_short_dropped(self, empty_excluded_urls: Path) -> None:
        short = _doc(source_item_id="short", text=_long_text(50))
        cfg = FilterConfig(
            today=date(2026, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([short], cfg)
        assert report.kept == []
        assert len(report.dropped) == 1
        dropped_doc, reason = report.dropped[0]
        assert dropped_doc == short
        assert reason == "too_short"

    def test_too_long_flagged_but_kept(self, empty_excluded_urls: Path) -> None:
        huge = _doc(source_item_id="huge", text=_long_text(60_000))
        cfg = FilterConfig(
            today=date(2026, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([huge], cfg)
        assert report.kept == [huge]
        assert report.dropped == []
        assert len(report.flagged_for_review) == 1
        flagged_doc, reason = report.flagged_for_review[0]
        assert flagged_doc == huge
        assert reason == "too_long"

    def test_excluded_url_dropped(self, tmp_path: Path) -> None:
        excluded = tmp_path / "excluded_urls.yaml"
        excluded.write_text(
            "urls:\n  - https://example.com/banned\n"
        )
        banned = _doc(
            source_item_id="banned",
            canonical_url="https://example.com/banned",
            text=_long_text(500),
        )
        ok = _doc(
            source_item_id="ok",
            canonical_url="https://example.com/ok",
            text=_long_text(500),
            hash_seed="b",
        )
        cfg = FilterConfig(today=date(2026, 5, 14), excluded_urls_path=excluded)
        report = apply_filters([banned, ok], cfg)
        assert report.kept == [ok]
        assert len(report.dropped) == 1
        dropped_doc, reason = report.dropped[0]
        assert dropped_doc == banned
        assert reason == "excluded"

    def test_today_controls_recency(self, empty_excluded_urls: Path) -> None:
        doc = _doc(
            source_item_id="boundary",
            last_modified_at=date(2014, 5, 15),
            text=_long_text(500),
        )
        # Pretend today is 2024-05-14: doc is ~10 years old. With default
        # max_age_years=10, last_modified_at is on the boundary and kept.
        cfg = FilterConfig(
            today=date(2024, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([doc], cfg)
        assert report.kept == [doc]
        assert report.dropped == []

    def test_today_drops_when_far_future(self, empty_excluded_urls: Path) -> None:
        doc = _doc(
            source_item_id="aged",
            last_modified_at=date(2014, 5, 14),
            text=_long_text(500),
        )
        # Pretend today is 2040 - doc is 26 years old, must be dropped.
        cfg = FilterConfig(
            today=date(2040, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([doc], cfg)
        assert report.kept == []
        assert report.dropped[0][1] == "too_old"

    def test_doc_with_no_last_modified_kept_by_recency(
        self, empty_excluded_urls: Path
    ) -> None:
        # Missing date can't be "too old" - we keep it (recency can't be
        # evaluated). Quality filters still apply.
        doc = _doc(
            source_item_id="undated",
            last_modified_at=None,
            text=_long_text(500),
        )
        cfg = FilterConfig(
            today=date(2026, 5, 14),
            excluded_urls_path=empty_excluded_urls,
        )
        report = apply_filters([doc], cfg)
        assert report.kept == [doc]
