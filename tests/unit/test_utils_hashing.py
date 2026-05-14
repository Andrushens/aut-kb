from __future__ import annotations

from autism_corpus.utils.hashing import canonical_text_hash, url_cache_key


class TestCanonicalTextHash:
    def test_stable_across_whitespace_variants(self) -> None:
        a = canonical_text_hash("Hello,   world!\n\n\nThis is a test.\n")
        b = canonical_text_hash("Hello, world! This is a test.")
        assert a == b

    def test_strips_trailing_whitespace_per_line(self) -> None:
        assert canonical_text_hash("foo  \nbar\t") == canonical_text_hash("foo\nbar")

    def test_case_sensitive(self) -> None:
        assert canonical_text_hash("Autism") != canonical_text_hash("autism")

    def test_returns_64_hex_chars(self) -> None:
        h = canonical_text_hash("hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_content_different_hash(self) -> None:
        assert canonical_text_hash("a") != canonical_text_hash("b")


class TestUrlCacheKey:
    def test_stable_for_same_url(self) -> None:
        a = url_cache_key("https://www.nhs.uk/conditions/autism/")
        b = url_cache_key("https://www.nhs.uk/conditions/autism/")
        assert a == b

    def test_differs_for_different_url(self) -> None:
        a = url_cache_key("https://www.nhs.uk/conditions/autism/")
        b = url_cache_key("https://www.nhs.uk/conditions/autism/signs/")
        assert a != b

    def test_returns_64_hex_chars(self) -> None:
        assert len(url_cache_key("https://x.test/y")) == 64
