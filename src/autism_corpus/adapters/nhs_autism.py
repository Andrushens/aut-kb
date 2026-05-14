"""NHS autism adapter.

Discovers autism-related pages from the NHS sitemap, fetches the HTML, and
emits ParsedDocument records under the Open Government Licence v3.0.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef

_SITEMAP_URL = "https://www.nhs.uk/sitemap.xml"
_AUTISM_PATH_PREFIX = "/conditions/autism/"
_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@register_adapter
class NhsAutismAdapter(SourceAdapter):
    """Adapter for NHS conditions/autism pages."""

    source_id: ClassVar[str] = "nhs-autism"
    licence: ClassVar[str] = "OGL-UK-3.0"
    licence_url: ClassVar[str] = (
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
    )
    attribution_template: ClassVar[str] = (
        "Information from NHS Digital, licenced under the Open Government Licence v3.0"
    )

    def discover(self) -> Iterator[SourceItemRef]:
        sitemap = http_get_as_raw_document(
            self.http_client,
            source_id=self.source_id,
            source_item_id="sitemap",
            url=_SITEMAP_URL,
        )
        root = ET.fromstring(sitemap.payload)
        for loc in root.findall(".//sm:url/sm:loc", _SITEMAP_NS):
            url = (loc.text or "").strip()
            if not url:
                continue
            path = urlsplit(url).path
            if not path.startswith(_AUTISM_PATH_PREFIX):
                continue
            item_id = path.lstrip("/")
            yield SourceItemRef(source_id=self.source_id, item_id=item_id, url=url)

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        if ref.url is None:
            raise ValueError(f"ref {ref.item_id!r} has no url")
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
