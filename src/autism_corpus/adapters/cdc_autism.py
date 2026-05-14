"""CDC autism pages adapter.

Discovers URLs under ``cdc.gov/autism/`` and ``cdc.gov/ncbddd/autism/`` via
the CDC sitemap index. Treats CDC content as US-Government public-domain.
"""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_DEFAULT_SITEMAP_URL = "https://www.cdc.gov/sitemap.xml"
_AUTISM_PATH_MARKERS = ("/autism/", "/ncbddd/autism/")


def _is_autism_url(url: str) -> bool:
    return any(marker in url for marker in _AUTISM_PATH_MARKERS)


def _parse_xml(payload: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.fromstring(payload, parser=parser)


def _extract_locs(root: etree._Element, tag: str) -> list[str]:
    locs: list[str] = []
    for el in root.iterfind(f".//sm:{tag}/sm:loc", namespaces=_SITEMAP_NS):
        if el.text:
            locs.append(el.text.strip())
    return locs


def _item_id_from_url(url: str) -> str:
    # Stable, readable id derived from URL path.
    path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else url
    cleaned = path.rstrip("/").replace("/", "_") or "index"
    if cleaned.endswith(".html"):
        cleaned = cleaned[: -len(".html")]
    return cleaned or "index"


@register_adapter
class CdcAutismAdapter(SourceAdapter):
    source_id = "cdc-autism"
    licence = "public-domain"
    licence_url = "https://www.cdc.gov/other/agencymaterials.html"
    attribution_template = "U.S. Centers for Disease Control and Prevention (public domain)"

    def __init__(
        self,
        http_client: CachedHttpClient,
        *,
        sitemap_url: str = _DEFAULT_SITEMAP_URL,
    ) -> None:
        super().__init__(http_client)
        self._sitemap_url = sitemap_url

    def discover(self) -> Iterator[SourceItemRef]:
        index_payload = self.http_client.get(self._sitemap_url).payload
        index_root = _parse_xml(index_payload)
        sub_locs = _extract_locs(index_root, "sitemap")

        # Prefer a sub-sitemap whose URL mentions autism, fall back to all.
        autism_subs = [loc for loc in sub_locs if "autism" in loc.lower()]
        chosen = autism_subs or sub_locs

        seen: set[str] = set()
        for sub_url in chosen:
            sub_payload = self.http_client.get(sub_url).payload
            sub_root = _parse_xml(sub_payload)
            for page_url in _extract_locs(sub_root, "url"):
                if not _is_autism_url(page_url):
                    continue
                if page_url in seen:
                    continue
                seen.add(page_url)
                yield SourceItemRef(
                    source_id=self.source_id,
                    item_id=_item_id_from_url(page_url),
                    url=page_url,
                )

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        if ref.url is None:
            raise ValueError(f"CdcAutismAdapter requires ref.url for {ref.item_id!r}")
        return http_get_as_raw_document(
            self.http_client,
            source_id=self.source_id,
            source_item_id=ref.item_id,
            url=ref.url,
        )

    def parse(self, raw: RawDocument) -> ParsedDocument:
        return build_parsed_document(
            raw,
            source_id=self.source_id,
            licence=self.licence,
            licence_url=self.licence_url,
            attribution=self.attribution_template,
            content_type="patient-info",
            medical_disclaimer_required=False,
            payload_kind="html",
        )
