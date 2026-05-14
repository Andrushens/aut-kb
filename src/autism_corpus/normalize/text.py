"""Plain-text normalisation helpers."""

from __future__ import annotations

import re
from functools import lru_cache

from lingua import LanguageDetector, LanguageDetectorBuilder

# Runs of spaces and tabs (not newlines).
_HORIZONTAL_WS_RUN = re.compile(r"[ \t]+")
# Trailing horizontal whitespace before a newline.
_TRAILING_WS = re.compile(r"[ \t]+\n")
# 3+ consecutive newlines collapse to exactly 2.
_NEWLINE_RUN = re.compile(r"\n{3,}")
# Minimum number of word characters required before we attempt language detection.
_MIN_DETECT_CHARS = 10


def normalize_whitespace(text: str) -> str:
    """Collapse horizontal whitespace runs, trim per-line, and cap newline runs.

    Specifically:
    - Collapse runs of spaces and tabs to a single space.
    - Strip trailing whitespace from each line.
    - Collapse 3+ consecutive newlines to exactly 2.
    - Strip surrounding whitespace from the entire string.
    """
    if not text:
        return ""
    out = _HORIZONTAL_WS_RUN.sub(" ", text)
    out = _TRAILING_WS.sub("\n", out)
    out = _NEWLINE_RUN.sub("\n\n", out)
    return out.strip()


@lru_cache(maxsize=1)
def _detector() -> LanguageDetector:
    """Build a lingua detector once. Cached to avoid re-loading models per call."""
    return LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()


def detect_language(text: str) -> str:
    """Return ISO 639-1 code via lingua, or ``"und"`` when undetermined.

    Operates on plain text only; never inspects HTML attributes.
    """
    stripped = text.strip()
    if len(stripped) < _MIN_DETECT_CHARS:
        return "und"
    detected = _detector().detect_language_of(stripped)
    if detected is None:
        return "und"
    code: str = detected.iso_code_639_1.name.lower()
    return code
