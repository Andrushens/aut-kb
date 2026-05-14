from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


class RobotsCache:
    """Per-host robots.txt cache wrapping urllib.robotparser.

    The standard library's RobotFileParser is fine but doesn't cache and
    insists on opening URLs itself. We override _fetch so HTTP calls go through
    httpx with our User-Agent, and we cache the parsed result per host.

    Limitation: stdlib's RobotFileParser uses first-match order rather than
    RFC 9309 longest-match. When a site lists `Disallow:` before a matching
    `Allow:` line, the Disallow wins. For our polite-crawler use case this is
    the safer default.
    """

    def __init__(self, user_agent: str, timeout: float = 10.0) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._parsers: dict[str, RobotFileParser] = {}

    def _fetch(self, host_url: str) -> str:
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
            response = client.get(host_url)
            if response.status_code >= 400:
                return ""
            return response.text

    def _parser_for(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        host_key = f"{parts.scheme}://{parts.netloc}"
        cached = self._parsers.get(host_key)
        if cached is not None:
            return cached

        parser = RobotFileParser()
        parser.set_url(f"{host_key}/robots.txt")
        body = self._fetch(f"{host_key}/robots.txt")
        parser.parse(body.splitlines())
        self._parsers[host_key] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        parser = self._parser_for(url)
        return parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        parser = self._parser_for(url)
        delay = parser.crawl_delay(self.user_agent)
        if delay is None:
            return None
        return float(delay)

    def _cache_size(self) -> int:
        return len(self._parsers)
