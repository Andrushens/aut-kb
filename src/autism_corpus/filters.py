from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import tiktoken
import yaml
from tiktoken import Encoding

from autism_corpus.config import DEFAULT_DATA_DIR
from autism_corpus.models import ParsedDocument


@lru_cache(maxsize=4)
def _get_encoding(name: str) -> Encoding:
    return tiktoken.get_encoding(name)


@dataclass(frozen=True)
class FilterConfig:
    max_age_years: int = 10
    min_tokens: int = 200
    max_tokens: int = 50_000
    excluded_urls_path: Path = DEFAULT_DATA_DIR / "excluded_urls.yaml"
    today: date | None = None


@dataclass(frozen=True)
class FilterReport:
    kept: list[ParsedDocument] = field(default_factory=list)
    dropped: list[tuple[ParsedDocument, str]] = field(default_factory=list)
    flagged_for_review: list[tuple[ParsedDocument, str]] = field(default_factory=list)


_DEFAULT_FILTER_CONFIG = FilterConfig()


def _load_excluded_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    raw: Any = yaml.safe_load(path.read_text()) or {}
    urls = raw.get("urls", []) if isinstance(raw, dict) else []
    if not isinstance(urls, list):
        return set()
    return {str(u) for u in urls}


def _is_too_old(
    doc: ParsedDocument, *, today: date, max_age_years: int
) -> bool:
    """A document is "too old" if more than *max_age_years* calendar years
    have elapsed between its ``last_modified_at`` and *today*.

    Calendar-year semantics: a doc dated 2014-05-14 is exactly 10 years old on
    2024-05-14 (still allowed) and becomes too old on 2024-05-15.
    """
    if doc.last_modified_at is None:
        return False
    src = doc.last_modified_at
    try:
        threshold = src.replace(year=src.year + max_age_years)
    except ValueError:
        # Source date is Feb 29 on a leap year; use Feb 28 in non-leap target.
        threshold = src.replace(year=src.year + max_age_years, day=28)
    return today > threshold


def apply_filters(
    docs: Iterable[ParsedDocument],
    config: FilterConfig = _DEFAULT_FILTER_CONFIG,
    tokenizer_name: str = "cl100k_base",
) -> FilterReport:
    """Apply excluded-URL, recency, and quality filters.

    Returns a :class:`FilterReport` with three lists:
      * ``kept`` - documents that passed all hard filters.
      * ``dropped`` - ``(doc, reason)`` for filtered-out documents. Reasons:
        ``"excluded"``, ``"too_old"``, ``"too_short"``.
      * ``flagged_for_review`` - kept-but-flagged documents (e.g. ``"too_long"``).
    """
    excluded_urls = _load_excluded_urls(config.excluded_urls_path)
    today = config.today if config.today is not None else date.today()
    enc = _get_encoding(tokenizer_name)

    kept: list[ParsedDocument] = []
    dropped: list[tuple[ParsedDocument, str]] = []
    flagged: list[tuple[ParsedDocument, str]] = []

    for doc in docs:
        if doc.canonical_url in excluded_urls:
            dropped.append((doc, "excluded"))
            continue
        if doc.content_type != "clinical-guideline" and _is_too_old(
            doc, today=today, max_age_years=config.max_age_years
        ):
            dropped.append((doc, "too_old"))
            continue
        token_count = len(enc.encode(doc.text))
        if token_count < config.min_tokens:
            dropped.append((doc, "too_short"))
            continue
        kept.append(doc)
        if token_count > config.max_tokens:
            flagged.append((doc, "too_long"))

    return FilterReport(kept=kept, dropped=dropped, flagged_for_review=flagged)
