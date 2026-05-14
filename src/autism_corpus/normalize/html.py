"""HTML main-content extraction.

Uses trafilatura for boilerplate removal and markdown-style rendering of
headings and lists, and selectolax for two side-channels:
- collecting ``<img alt>`` text from the main content, in document order
- parsing ``<meta http-equiv="last-modified">`` / ``<meta name="last-modified">``
  date tags as a fallback last-modified signal
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import trafilatura
from selectolax.parser import HTMLParser, Node

from autism_corpus.normalize.text import normalize_whitespace

# Selectors for boilerplate regions whose images and meta we want to ignore.
_BOILERPLATE_SELECTORS = (
    "nav",
    "header",
    "footer",
    "aside",
    "[class*='cookie']",
    "[id*='cookie']",
    "[class*='share']",
    "[id*='share']",
)


@dataclass(frozen=True)
class HtmlExtraction:
    """Structured result of HTML normalisation."""

    title: str
    text: str
    figures: list[str]
    last_modified: date | None


def _strip_boilerplate(tree: HTMLParser) -> None:
    """Remove navigation, footer, cookie banners, share widgets in-place."""
    for selector in _BOILERPLATE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()


def _main_content_root(tree: HTMLParser) -> Node | None:
    """Locate the most specific main-content container we can find."""
    for selector in ("main article", "article", "main", "body"):
        node = tree.css_first(selector)
        if node is not None:
            return node
    return None


def _collect_figure_alts(tree: HTMLParser) -> list[str]:
    """Return non-empty alt text for ``<img>`` elements in document order."""
    root = _main_content_root(tree)
    if root is None:
        return []
    alts: list[str] = []
    for img in root.css("img"):
        alt = img.attributes.get("alt")
        if alt:
            alts.append(alt.strip())
    return alts


def _parse_last_modified(tree: HTMLParser) -> date | None:
    """Return the date in a last-modified meta tag, if any.

    Recognises ``<meta name="last-modified" content="YYYY-MM-DD">`` and
    ``<meta http-equiv="last-modified" content="...">``.
    """
    for meta in tree.css("meta"):
        attrs = meta.attributes
        name = (attrs.get("name") or attrs.get("http-equiv") or "").lower()
        if name != "last-modified":
            continue
        content = attrs.get("content")
        if not content:
            continue
        return _coerce_date(content.strip())
    return None


def _coerce_date(raw: str) -> date | None:
    """Parse a date string in a couple of common formats."""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _extract_main_text(html: str, url: str | None) -> str:
    """Run trafilatura to get the main content in markdown form."""
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_images=False,
        include_links=False,
        include_tables=False,
        favor_recall=True,
    )
    return extracted or ""


def _extract_title(html: str, tree: HTMLParser) -> str:
    """Prefer trafilatura's metadata title; fall back to <title>; then h1."""
    meta = trafilatura.extract_metadata(html)
    if meta is not None and meta.title:
        return meta.title.strip()
    title_node = tree.css_first("title")
    if title_node is not None and title_node.text():
        return title_node.text().strip()
    h1 = tree.css_first("h1")
    if h1 is not None and h1.text():
        return h1.text().strip()
    return ""


# Defensive scrub for any HTML that slips through the markdown renderer.
_TAG_RE = re.compile(r"<[^>]+>")


def extract_html(html: str, *, url: str | None = None) -> HtmlExtraction:
    """Extract main content, title, figure alt text, and last-modified date."""
    tree = HTMLParser(html)
    _strip_boilerplate(tree)

    figures = _collect_figure_alts(tree)
    last_modified = _parse_last_modified(tree)
    title = _extract_title(html, tree)

    raw_text = _extract_main_text(html, url)
    # Defensive: drop any stray HTML tags trafilatura missed.
    cleaned = _TAG_RE.sub("", raw_text)
    text = normalize_whitespace(cleaned)

    return HtmlExtraction(
        title=title,
        text=text,
        figures=figures,
        last_modified=last_modified,
    )
