from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from autism_corpus.dedup import deduplicate
from autism_corpus.models import ParsedDocument


def _doc(
    *,
    source_id: str = "nhs-autism",
    source_item_id: str = "x",
    licence: str = "OGL-UK-3.0",
    text_hash_seed: str = "a",
) -> ParsedDocument:
    kwargs: dict[str, Any] = {
        "source_id": source_id,
        "source_item_id": source_item_id,
        "canonical_url": f"https://example.com/{source_id}/{source_item_id}",
        "title": "Title",
        "text": "Some body text.",
        "language": "en",
        "published_at": date(2023, 1, 1),
        "last_modified_at": date(2024, 1, 1),
        "licence": licence,
        "licence_url": "https://example.com/licence",
        "attribution": "Attribution string",
        "content_type": "patient-info",
        "medical_disclaimer_required": False,
        "hash": text_hash_seed * 64,
        "fetched_at": datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
    }
    return ParsedDocument(**kwargs)


class TestDeduplicate:
    def test_same_hash_keeps_cleaner_licence(self) -> None:
        dirty = _doc(
            source_id="src-a",
            source_item_id="1",
            licence="CC-BY-NC-SA-3.0-IGO",
            text_hash_seed="a",
        )
        clean = _doc(
            source_id="src-b",
            source_item_id="2",
            licence="public-domain",
            text_hash_seed="a",
        )
        result = deduplicate([dirty, clean])
        assert result == [clean]

    def test_same_hash_cleaner_licence_when_clean_seen_first(self) -> None:
        clean = _doc(
            source_id="src-a",
            source_item_id="1",
            licence="CC0-1.0",
            text_hash_seed="a",
        )
        dirty = _doc(
            source_id="src-b",
            source_item_id="2",
            licence="CC-BY-SA-4.0",
            text_hash_seed="a",
        )
        result = deduplicate([clean, dirty])
        assert result == [clean]

    def test_distinct_hashes_all_kept_in_order(self) -> None:
        a = _doc(source_id="src-a", source_item_id="1", text_hash_seed="a")
        b = _doc(source_id="src-b", source_item_id="2", text_hash_seed="b")
        c = _doc(source_id="src-c", source_item_id="3", text_hash_seed="c")
        result = deduplicate([a, b, c])
        assert result == [a, b, c]

    def test_same_hash_same_licence_keeps_first_seen(self) -> None:
        first = _doc(
            source_id="src-first",
            source_item_id="1",
            licence="CC-BY-4.0",
            text_hash_seed="a",
        )
        second = _doc(
            source_id="src-second",
            source_item_id="2",
            licence="CC-BY-4.0",
            text_hash_seed="a",
        )
        result = deduplicate([first, second])
        assert result == [first]

    def test_stable_order_across_distinct_groups(self) -> None:
        # Interleave duplicates of two distinct hashes. The output order
        # follows the position at which each hash first appeared.
        a1 = _doc(source_id="src-a1", source_item_id="1", text_hash_seed="a")
        b1 = _doc(source_id="src-b1", source_item_id="1", text_hash_seed="b")
        a2 = _doc(
            source_id="src-a2",
            source_item_id="2",
            licence="public-domain",
            text_hash_seed="a",
        )
        b2 = _doc(
            source_id="src-b2",
            source_item_id="2",
            licence="public-domain",
            text_hash_seed="b",
        )
        result = deduplicate([a1, b1, a2, b2])
        # a-group winner is a2 (public-domain), b-group winner is b2.
        # Order: a-group first (hash 'a' seen first in input), then b-group.
        assert result == [a2, b2]
