from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
import respx

from autism_corpus.config import HttpConfig
from autism_corpus.utils.http import CachedHttpClient


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def fast_config() -> HttpConfig:
    # Very fast rate to keep tests quick; rate-limit assertion below uses 10/s.
    return HttpConfig(
        per_host_rate_per_second=10.0,
        cache_ttl_seconds=3600,
        request_timeout_seconds=5.0,
        max_retries=2,
    )


class TestCachedHttpClient:
    @respx.mock
    def test_sends_configured_user_agent(self, cache_dir: Path, fast_config: HttpConfig) -> None:
        route = respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="hi"))
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        client.get("https://nhs.uk/a")
        assert route.called
        sent_ua = route.calls.last.request.headers["user-agent"]
        assert sent_ua == fast_config.user_agent

    @respx.mock
    def test_returns_response_body(self, cache_dir: Path, fast_config: HttpConfig) -> None:
        respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="hello"))
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        result = client.get("https://nhs.uk/a")
        assert result.payload == b"hello"
        assert result.status_code == 200

    @respx.mock
    def test_caches_to_disk_after_first_call(
        self, cache_dir: Path, fast_config: HttpConfig
    ) -> None:
        route = respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="hello"))
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        client.get("https://nhs.uk/a")
        client.get("https://nhs.uk/a")
        assert route.call_count == 1  # second call served from cache

    @respx.mock
    def test_force_bypasses_cache(self, cache_dir: Path, fast_config: HttpConfig) -> None:
        route = respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="hello"))
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        client.get("https://nhs.uk/a")
        client.get("https://nhs.uk/a", force=True)
        assert route.call_count == 2

    @respx.mock
    def test_revalidates_with_etag_returning_304(
        self, cache_dir: Path, fast_config: HttpConfig
    ) -> None:
        # First call returns a body with an ETag.
        first = httpx.Response(200, text="v1", headers={"ETag": '"abc"'})
        route = respx.get("https://nhs.uk/a").mock(return_value=first)
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        client.get("https://nhs.uk/a")

        # Force the cache to look stale.
        client._mark_stale("https://nhs.uk/a")  # type: ignore[attr-defined]

        # Subsequent call should send If-None-Match and we return 304.
        route.mock(return_value=httpx.Response(304))
        result = client.get("https://nhs.uk/a")
        assert result.payload == b"v1"  # still get the cached body
        last = route.calls.last.request
        assert last.headers.get("if-none-match") == '"abc"'

    @respx.mock
    def test_retries_on_5xx(self, cache_dir: Path, fast_config: HttpConfig) -> None:
        responses = [
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, text="ok"),
        ]
        route = respx.get("https://nhs.uk/a").mock(side_effect=responses)
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        result = client.get("https://nhs.uk/a")
        assert result.payload == b"ok"
        assert route.call_count == 3

    @respx.mock
    def test_gives_up_after_max_retries(self, cache_dir: Path, fast_config: HttpConfig) -> None:
        respx.get("https://nhs.uk/a").mock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)]
        )
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        with pytest.raises(httpx.HTTPStatusError):
            client.get("https://nhs.uk/a")

    @respx.mock
    def test_rate_limit_spaces_requests_per_host(
        self, cache_dir: Path, fast_config: HttpConfig
    ) -> None:
        respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="a"))
        respx.get("https://nhs.uk/b").mock(return_value=httpx.Response(200, text="b"))
        # 10 req/s => min spacing 0.1s between requests to same host.
        client = CachedHttpClient(source_id="nhs-autism", cache_dir=cache_dir, config=fast_config)
        start = time.monotonic()
        client.get("https://nhs.uk/a")
        client.get("https://nhs.uk/b")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09  # allow a tiny slop below the 0.1s floor

    @respx.mock
    def test_rate_limit_independent_per_host(
        self, cache_dir: Path, fast_config: HttpConfig
    ) -> None:
        slow = HttpConfig(per_host_rate_per_second=2.0)  # 0.5s spacing per host
        respx.get("https://nhs.uk/a").mock(return_value=httpx.Response(200, text="a"))
        respx.get("https://cdc.gov/a").mock(return_value=httpx.Response(200, text="b"))
        client = CachedHttpClient(source_id="multi", cache_dir=cache_dir, config=slow)
        start = time.monotonic()
        client.get("https://nhs.uk/a")
        client.get("https://cdc.gov/a")
        elapsed = time.monotonic() - start
        # No throttling expected between different hosts.
        assert elapsed < 0.4
