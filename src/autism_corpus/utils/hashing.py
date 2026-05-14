from __future__ import annotations

import hashlib
import re

_WHITESPACE_RUN = re.compile(r"[ \t]+")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINES = re.compile(r"\n{2,}")


def _normalise(text: str) -> str:
    """Canonicalise text for hashing: collapse internal whitespace runs, strip
    trailing whitespace per line, collapse blank-line runs to a single space.

    The goal is for hashes to be stable across cosmetic whitespace differences
    so the same article from two mirrors deduplicates cleanly.
    """
    s = _TRAILING_WS.sub("", text)
    s = _BLANK_LINES.sub(" ", s)
    s = s.replace("\n", " ")
    s = _WHITESPACE_RUN.sub(" ", s)
    return s.strip()


def canonical_text_hash(text: str) -> str:
    return hashlib.sha256(_normalise(text).encode("utf-8")).hexdigest()


def url_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
