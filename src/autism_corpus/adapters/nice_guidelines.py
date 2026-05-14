"""NICE clinical guidelines adapter.

Reads a curated list of guideline PDFs from `data/seed_urls.yaml`, fetches
the PDFs, and emits ParsedDocument records under the Open Government
Licence v3.0 with the medical-disclaimer flag set.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

import yaml

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.config import DEFAULT_DATA_DIR
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef

_SEED_FILE = DEFAULT_DATA_DIR / "seed_urls.yaml"
_SEED_KEY = "nice-guidelines"


def _load_seed_entries() -> list[dict[str, Any]]:
    if not _SEED_FILE.exists():
        return []
    raw = yaml.safe_load(_SEED_FILE.read_text()) or {}
    entries = raw.get(_SEED_KEY) or []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


@register_adapter
class NiceGuidelinesAdapter(SourceAdapter):
    """Adapter for NICE clinical guidelines (PDFs)."""

    source_id: ClassVar[str] = "nice-guidelines"
    licence: ClassVar[str] = "OGL-UK-3.0"
    licence_url: ClassVar[str] = (
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
    )
    attribution_template: ClassVar[str] = (
        "From NICE clinical guidelines, licenced under the Open Government Licence v3.0"
    )

    def discover(self) -> Iterator[SourceItemRef]:
        for entry in _load_seed_entries():
            item_id = entry.get("item_id")
            url = entry.get("url")
            if not item_id or not url:
                continue
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
            content_type="clinical-guideline",
            medical_disclaimer_required=True,
            payload_kind="pdf",
        )
