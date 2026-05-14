from __future__ import annotations

import pytest

from autism_corpus.utils.robots import RobotsCache

_ROBOTS_SPECIFIC = """User-agent: *
Disallow: /private/
Allow: /private/public/

User-agent: autism-corpus
Disallow: /no-bots/
Crawl-delay: 5
"""

_ROBOTS_WILDCARD_ONLY = """User-agent: *
Disallow: /private/
Allow: /private/public/
Crawl-delay: 2
"""


def _make_cache(monkeypatch: pytest.MonkeyPatch, body: str, ua: str) -> RobotsCache:
    def fake_fetch(self: RobotsCache, host_url: str) -> str:
        return body

    monkeypatch.setattr(RobotsCache, "_fetch", fake_fetch, raising=True)
    return RobotsCache(user_agent=ua)


class TestRobotsCacheSpecificUA:
    """A robots.txt with a specific UA section overrides * for that UA (RFC 9309)."""

    @pytest.fixture
    def cache(self, monkeypatch: pytest.MonkeyPatch) -> RobotsCache:
        return _make_cache(monkeypatch, _ROBOTS_SPECIFIC, "autism-corpus")

    def test_allows_public_path(self, cache: RobotsCache) -> None:
        assert cache.can_fetch("https://example.test/articles/x")

    def test_blocks_paths_disallowed_for_our_ua(self, cache: RobotsCache) -> None:
        assert not cache.can_fetch("https://example.test/no-bots/x")

    def test_wildcard_disallow_does_not_apply_when_specific_section_exists(
        self, cache: RobotsCache
    ) -> None:
        assert cache.can_fetch("https://example.test/private/secret")

    def test_crawl_delay_for_our_ua(self, cache: RobotsCache) -> None:
        assert cache.crawl_delay("https://example.test/x") == 5.0


class TestRobotsCacheWildcardOnly:
    """When robots.txt has only `*`, those rules apply to any UA."""

    @pytest.fixture
    def cache(self, monkeypatch: pytest.MonkeyPatch) -> RobotsCache:
        return _make_cache(monkeypatch, _ROBOTS_WILDCARD_ONLY, "autism-corpus")

    def test_blocks_wildcard_disallow(self, cache: RobotsCache) -> None:
        assert not cache.can_fetch("https://example.test/private/secret")

    def test_crawl_delay_from_wildcard(self, cache: RobotsCache) -> None:
        assert cache.crawl_delay("https://example.test/x") == 2.0


class TestRobotsCacheCaching:
    def test_caches_per_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = _make_cache(monkeypatch, _ROBOTS_WILDCARD_ONLY, "autism-corpus")
        cache.can_fetch("https://example.test/x")
        cache.can_fetch("https://example.test/y")
        cache.can_fetch("https://other.test/x")
        assert cache._cache_size() == 2
