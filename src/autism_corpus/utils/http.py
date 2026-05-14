from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from autism_corpus.config import HttpConfig
from autism_corpus.utils.hashing import url_cache_key


@dataclass(frozen=True)
class FetchResult:
    url: str
    payload: bytes
    status_code: int
    content_type: str | None
    fetched_at: datetime
    from_cache: bool


class _HostRateLimiter:
    """Per-host token bucket: enforces minimum spacing between requests."""

    def __init__(self, per_host_rate_per_second: float) -> None:
        self._spacing = 1.0 / per_host_rate_per_second
        self._next_allowed: dict[str, float] = {}

    def acquire(self, host: str) -> None:
        now = time.monotonic()
        ready = self._next_allowed.get(host, 0.0)
        if now < ready:
            time.sleep(ready - now)
            now = time.monotonic()
        self._next_allowed[host] = now + self._spacing


class CachedHttpClient:
    """Polite HTTP client used by every source adapter.

    Responsibilities:
    - Pin a User-Agent that identifies the crawler to source operators.
    - Per-host token-bucket rate limiting.
    - Content-addressed on-disk cache with ETag/Last-Modified revalidation.
    - Retry on 5xx and transient network errors up to `config.max_retries`.
    """

    def __init__(
        self,
        source_id: str,
        cache_dir: Path,
        config: HttpConfig | None = None,
    ) -> None:
        self.source_id = source_id
        self.config = config or HttpConfig()
        self._cache_root = cache_dir / source_id
        self._cache_root.mkdir(parents=True, exist_ok=True)
        self._limiter = _HostRateLimiter(self.config.per_host_rate_per_second)
        self._client = httpx.Client(
            timeout=self.config.request_timeout_seconds,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )

    # ------------------------------------------------------------------ helpers
    def _paths_for(self, url: str) -> tuple[Path, Path]:
        key = url_cache_key(url)
        return self._cache_root / f"{key}.raw", self._cache_root / f"{key}.meta.json"

    def _load_cache(self, url: str) -> tuple[bytes, dict[str, Any]] | None:
        body_path, meta_path = self._paths_for(url)
        if not body_path.exists() or not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        return body_path.read_bytes(), meta

    def _write_cache(
        self,
        url: str,
        payload: bytes,
        meta: dict[str, Any],
    ) -> None:
        body_path, meta_path = self._paths_for(url)
        body_path.write_bytes(payload)
        meta_path.write_text(json.dumps(meta, sort_keys=True))

    def _cache_is_fresh(self, meta: dict[str, Any]) -> bool:
        if meta.get("stale"):
            return False
        cached_at = meta.get("fetched_at")
        if not cached_at:
            return False
        try:
            ts = datetime.fromisoformat(cached_at)
        except ValueError:
            return False
        age = (datetime.now(UTC) - ts).total_seconds()
        return age < self.config.cache_ttl_seconds

    def _mark_stale(self, url: str) -> None:
        """Test-only helper: mark a cache entry as stale to force revalidation."""
        _, meta_path = self._paths_for(url)
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text())
        meta["stale"] = True
        meta_path.write_text(json.dumps(meta, sort_keys=True))

    # ------------------------------------------------------------------ public
    def get(self, url: str, *, force: bool = False) -> FetchResult:
        host = urlsplit(url).netloc

        cached = self._load_cache(url) if not force else None
        if cached is not None and self._cache_is_fresh(cached[1]):
            payload, meta = cached
            return FetchResult(
                url=url,
                payload=payload,
                status_code=int(meta.get("status_code", 200)),
                content_type=meta.get("content_type"),
                fetched_at=datetime.fromisoformat(meta["fetched_at"]),
                from_cache=True,
            )

        request_headers: dict[str, str] = {}
        if cached is not None:
            _, meta = cached
            etag = meta.get("etag")
            last_modified = meta.get("last_modified")
            if etag:
                request_headers["If-None-Match"] = etag
            if last_modified:
                request_headers["If-Modified-Since"] = last_modified

        response = self._request_with_retries(url, host, request_headers)

        if response.status_code == 304 and cached is not None:
            payload, meta = cached
            meta = {**meta, "fetched_at": datetime.now(UTC).isoformat(), "stale": False}
            self._write_cache(url, payload, meta)
            return FetchResult(
                url=url,
                payload=payload,
                status_code=200,
                content_type=meta.get("content_type"),
                fetched_at=datetime.fromisoformat(meta["fetched_at"]),
                from_cache=True,
            )

        response.raise_for_status()
        payload = response.content
        fetched_at = datetime.now(UTC)
        meta = {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "fetched_at": fetched_at.isoformat(),
            "stale": False,
        }
        self._write_cache(url, payload, meta)
        return FetchResult(
            url=url,
            payload=payload,
            status_code=response.status_code,
            content_type=meta["content_type"],
            fetched_at=fetched_at,
            from_cache=False,
        )

    def _request_with_retries(
        self,
        url: str,
        host: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            self._limiter.acquire(host)
            try:
                response = self._client.get(url, headers=headers)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt == self.config.max_retries:
                    raise
                time.sleep(min(2**attempt * 0.05, 1.0))
                continue

            if response.status_code < 500 or response.status_code == 304:
                return response

            last_response = response
            if attempt == self.config.max_retries:
                response.raise_for_status()
            time.sleep(min(2**attempt * 0.05, 1.0))

        # Loop above always returns or raises before falling through, but mypy
        # needs an explicit terminator.
        if last_response is not None:  # pragma: no cover - defensive
            last_response.raise_for_status()
        raise RuntimeError("unreachable") from last_exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CachedHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
