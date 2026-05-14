"""PubMed Central Open Access Commercial-Use subset adapter.

The PMC Open Access Commercial-Use subset (NCBI FTP / AWS RODA bucket
``pmc-oa-opendata``) contains JATS XML for millions of biomedical articles.
For the autism knowledge corpus we want only:

- Article types that are review-like (review articles, systematic reviews,
  clinical guidelines) — not primary bench-science research.
- Articles under a Commercial-Use-friendly Creative Commons licence
  (CC0, CC-BY, CC-BY-SA, CC-BY-ND) — never CC-BY-NC.
- Articles whose MeSH terms / keywords / title / abstract mention autism.

Bulk acquisition (FTP/S3 download of the OA file list and per-article
tarballs) is delegated to two injected callables so this adapter remains
unit-testable without network access:

- ``file_list_source`` yields :class:`FileListEntry` rows; the production
  default would parse ``oa_file_list.csv`` from the OA bucket. Tests inject
  a small in-memory list.
- ``article_loader`` returns the raw JATS XML bytes for a given entry; the
  production default would download/untar the article package. Tests inject
  a callable that reads a fixture file.

The real PMC ``oa_file_list.csv`` does **not** include MeSH terms, so
``FileListEntry.mesh_terms`` is left empty in production; the autism filter
is applied at parse-time against ``<kwd-group>``, ``<article-title>``, and
``<abstract>`` text inside the JATS XML.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import ClassVar
from xml.etree import ElementTree as ET

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.normalize.text import detect_language, normalize_whitespace
from autism_corpus.utils.hashing import canonical_text_hash
from autism_corpus.utils.http import CachedHttpClient

# ---------------------------------------------------------------------------
# Public dataclasses and sentinel exception
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileListEntry:
    """One row of the PMC OA Commercial-Use file list.

    ``mesh_terms`` is typically empty in production because the real
    ``oa_file_list.csv`` does not include MeSH; the autism keyword filter
    runs at parse-time against the JATS XML body.
    """

    pmcid: str
    article_file: str
    licence: str
    article_type: str
    mesh_terms: list[str] = field(default_factory=list)


class PmcSkip(Exception):
    """Raised by :meth:`PmcOaAdapter.parse` when an article does not satisfy
    the autism MeSH/keyword filter. The pipeline catches this sentinel and
    drops the document without treating it as an error."""


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

AUTISM_KEYWORDS: frozenset[str] = frozenset(
    {
        "autism",
        "autism spectrum disorder",
        "asd",
        "autistic",
        "asperger",
        "asperger syndrome",
        "pervasive developmental disorder",
    }
)

ACCEPTED_ARTICLE_TYPES: frozenset[str] = frozenset(
    {"review-article", "systematic-review", "clinical-guideline"}
)

_LICENCE_MAP: dict[str, str] = {
    "CC0": "CC0-1.0",
    "CC BY": "CC-BY-4.0",
    "CC BY 4.0": "CC-BY-4.0",
    "CC-BY": "CC-BY-4.0",
    "CC BY-SA": "CC-BY-SA-4.0",
    "CC BY-ND": "CC-BY-ND-4.0",
}

COMMERCIAL_USE_OK: frozenset[str] = frozenset(_LICENCE_MAP.values())

_LICENCE_URL_BY_SPDX: dict[str, str] = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC-BY-ND-4.0": "https://creativecommons.org/licenses/by-nd/4.0/",
}


# ---------------------------------------------------------------------------
# Type aliases for injected callables
# ---------------------------------------------------------------------------

FileListSource = Callable[[], Iterable[FileListEntry]]
ArticleLoader = Callable[[FileListEntry], bytes]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


@register_adapter
class PmcOaAdapter(SourceAdapter):
    """Adapter for the PMC Open Access Commercial-Use subset."""

    source_id: ClassVar[str] = "pmc-oa-autism"
    licence: ClassVar[str] = "CC-BY-4.0"
    licence_url: ClassVar[str] = "https://creativecommons.org/licenses/by/4.0/"
    attribution_template: ClassVar[str] = "PubMed Central Open Access ({licence})"

    def __init__(
        self,
        http_client: CachedHttpClient,
        *,
        file_list_source: FileListSource | None = None,
        article_loader: ArticleLoader | None = None,
    ) -> None:
        super().__init__(http_client)
        if file_list_source is None:
            raise ValueError(
                "PmcOaAdapter requires a file_list_source callable; the bulk "
                "FTP/S3 default has not been implemented in this build."
            )
        if article_loader is None:
            raise ValueError(
                "PmcOaAdapter requires an article_loader callable; the bulk "
                "FTP/S3 default has not been implemented in this build."
            )
        self._file_list_source: FileListSource = file_list_source
        self._article_loader: ArticleLoader = article_loader

    # ------------------------------------------------------------------ discover
    def discover(self) -> Iterator[SourceItemRef]:
        """Yield refs for entries that pass the article-type and licence filters.

        The autism keyword filter is deferred to :meth:`parse` because it
        requires inspecting the article body XML.
        """
        for entry in self._file_list_source():
            if entry.article_type not in ACCEPTED_ARTICLE_TYPES:
                continue
            spdx = _LICENCE_MAP.get(entry.licence.strip())
            if spdx is None or spdx not in COMMERCIAL_USE_OK:
                continue
            yield SourceItemRef(
                source_id=self.source_id,
                item_id=entry.pmcid,
                url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{entry.pmcid}/",
            )

    # -------------------------------------------------------------------- fetch
    def fetch(self, ref: SourceItemRef) -> RawDocument:
        entry = self._find_entry(ref.item_id)
        payload = self._article_loader(entry)
        return RawDocument(
            source_id=self.source_id,
            source_item_id=entry.pmcid,
            url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{entry.pmcid}/",
            content_type_header="application/xml",
            payload=payload,
            fetched_at=datetime.now(UTC),
        )

    def _find_entry(self, pmcid: str) -> FileListEntry:
        for entry in self._file_list_source():
            if entry.pmcid == pmcid:
                return entry
        raise KeyError(f"no file_list entry for pmcid={pmcid!r}")

    # -------------------------------------------------------------------- parse
    def parse(self, raw: RawDocument) -> ParsedDocument:
        root = ET.fromstring(raw.payload)

        title = _extract_title(root)
        abstract_text = _extract_abstract_text(root)
        keywords = _extract_keywords(root)
        body_text = _extract_body_text(root)

        if not _matches_autism_keywords(title, abstract_text, keywords):
            raise PmcSkip(
                f"no autism keywords found in title/abstract/kwd for {raw.source_item_id}"
            )

        spdx_licence = _extract_spdx_licence(root)
        if spdx_licence is None:
            raise PmcSkip(
                f"no Commercial-Use-friendly licence for {raw.source_item_id}"
            )

        published_at = _extract_pub_date(root)

        # Compose the full text: title, abstract, body sections.
        text_parts: list[str] = []
        if abstract_text:
            text_parts.append("# Abstract")
            text_parts.append(abstract_text)
        if body_text:
            text_parts.append(body_text)
        text = normalize_whitespace("\n\n".join(text_parts))

        licence_url = _LICENCE_URL_BY_SPDX[spdx_licence]
        attribution = self.attribution_template.format(licence=spdx_licence)

        return ParsedDocument(
            source_id=self.source_id,
            source_item_id=raw.source_item_id,
            canonical_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{raw.source_item_id}/",
            title=title,
            text=text,
            language=detect_language(text),
            published_at=published_at,
            last_modified_at=None,
            licence=spdx_licence,
            licence_url=licence_url,
            attribution=attribution,
            content_type="research-article",
            medical_disclaimer_required=True,
            hash=canonical_text_hash(text),
            fetched_at=raw.fetched_at,
        )


# ---------------------------------------------------------------------------
# JATS XML extraction helpers
# ---------------------------------------------------------------------------


def _extract_title(root: ET.Element) -> str:
    el = root.find(".//front/article-meta/title-group/article-title")
    if el is None:
        return ""
    return _all_text(el).strip()


def _extract_abstract_text(root: ET.Element) -> str:
    abstract = root.find(".//front/article-meta/abstract")
    if abstract is None:
        return ""
    paragraphs = [
        _all_text(p).strip() for p in abstract.findall(".//p") if _all_text(p).strip()
    ]
    return "\n\n".join(paragraphs)


def _extract_keywords(root: ET.Element) -> list[str]:
    return [
        _all_text(kwd).strip()
        for kwd in root.findall(".//front/article-meta/kwd-group/kwd")
        if _all_text(kwd).strip()
    ]


def _extract_body_text(root: ET.Element) -> str:
    body = root.find("body")
    if body is None:
        return ""
    parts: list[str] = []
    for sec in body.findall("sec"):
        title_el = sec.find("title")
        if title_el is not None:
            title_text = _all_text(title_el).strip()
            if title_text:
                parts.append(f"## {title_text}")
        for p in sec.findall("p"):
            p_text = _all_text(p).strip()
            if p_text:
                parts.append(p_text)
    # Also include any top-level body paragraphs not inside a <sec>.
    for p in body.findall("p"):
        p_text = _all_text(p).strip()
        if p_text:
            parts.append(p_text)
    return "\n\n".join(parts)


def _all_text(el: ET.Element) -> str:
    """Concatenate all text under an element (depth-first), preserving order."""
    return "".join(el.itertext())


def _extract_pub_date(root: ET.Element) -> date | None:
    for pub_date in root.findall(".//front/article-meta/pub-date"):
        year_el = pub_date.find("year")
        if year_el is None or not (year_el.text or "").strip():
            continue
        try:
            year = int((year_el.text or "").strip())
        except ValueError:
            continue
        month_el = pub_date.find("month")
        day_el = pub_date.find("day")
        try:
            month = int((month_el.text or "1").strip()) if month_el is not None else 1
            day = int((day_el.text or "1").strip()) if day_el is not None else 1
            return date(year, month, day)
        except ValueError:
            try:
                return date(year, 1, 1)
            except ValueError:
                return None
    return None


def _extract_spdx_licence(root: ET.Element) -> str | None:
    """Read ``<permissions><license>`` and map the raw CC label to SPDX.

    JATS articles encode their licence in a few different shapes:
    - ``<license-ref>`` element with a URL
    - ``xlink:href`` attribute on ``<license>``
    - free-text inside ``<license-p>`` (the most common case for the PMC
      OA subset).
    We check each in turn.
    """
    license_el = root.find(".//front/article-meta/permissions/license")
    if license_el is None:
        return None

    # 1. <license-ref>
    ref_el = license_el.find("license-ref")
    if ref_el is not None and ref_el.text:
        spdx = _match_licence_text(ref_el.text)
        if spdx is not None:
            return spdx

    # 2. xlink:href attribute (with or without the xlink prefix expanded).
    for attr in ("{http://www.w3.org/1999/xlink}href", "href", "xlink:href"):
        href = license_el.get(attr)
        if href:
            spdx = _match_licence_text(href)
            if spdx is not None:
                return spdx

    # 3. <license-p> free text.
    for license_p in license_el.findall("license-p"):
        text = _all_text(license_p)
        spdx = _match_licence_text(text)
        if spdx is not None:
            return spdx

    return None


# Order matters: longer / more-specific labels first so "CC BY-SA" is matched
# before the shorter "CC BY" prefix, and "CC BY-NC" is recognised (and rejected
# by returning None) before "CC BY".
_LICENCE_PATTERNS: tuple[tuple[str, str | None], ...] = (
    ("cc by-nc-sa", None),
    ("cc by-nc-nd", None),
    ("cc by-nc", None),
    ("creative commons attribution-noncommercial", None),
    ("cc by-sa", "CC-BY-SA-4.0"),
    ("cc by-nd", "CC-BY-ND-4.0"),
    ("cc by 4.0", "CC-BY-4.0"),
    ("cc by", "CC-BY-4.0"),
    ("cc-by", "CC-BY-4.0"),
    ("cc0", "CC0-1.0"),
    ("creativecommons.org/publicdomain/zero", "CC0-1.0"),
    ("creativecommons.org/licenses/by-sa", "CC-BY-SA-4.0"),
    ("creativecommons.org/licenses/by-nd", "CC-BY-ND-4.0"),
    ("creativecommons.org/licenses/by-nc", None),
    ("creativecommons.org/licenses/by", "CC-BY-4.0"),
)


def _match_licence_text(text: str) -> str | None:
    """Return the SPDX label for the first matching pattern in ``text``.

    Patterns marked with ``None`` (e.g. NonCommercial variants) explicitly
    return ``None`` to reject the article.
    """
    lowered = text.lower()
    for needle, spdx in _LICENCE_PATTERNS:
        if needle in lowered:
            return spdx
    return None


def _matches_autism_keywords(
    title: str, abstract_text: str, keywords: list[str]
) -> bool:
    title_l = title.lower()
    abstract_l = abstract_text.lower()
    keyword_blob = " ".join(keywords).lower()
    return any(
        kw in title_l or kw in abstract_l or kw in keyword_blob
        for kw in AUTISM_KEYWORDS
    )
