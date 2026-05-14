"""MedlinePlus autism topic pages adapter.

Seeded from ``data/seed_urls.yaml`` under the ``medlineplus-autism:`` section.
We use the public HTML site (not the Connect API) so that content stays under
the standard MedlinePlus "free re-use" terms.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.config import DEFAULT_DATA_DIR
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient

_SEED_SECTION = "medlineplus-autism"


def _load_seed_entries(seed_path: Path, section: str) -> list[dict[str, Any]]:
    if not seed_path.exists():
        return []
    raw = yaml.safe_load(seed_path.read_text()) or {}
    entries = raw.get(section) or []
    if not isinstance(entries, list):
        raise ValueError(
            f"seed file {seed_path} section {section!r} must be a list, "
            f"got {type(entries).__name__}"
        )
    return [dict(entry) for entry in entries]


@register_adapter
class MedlinePlusAdapter(SourceAdapter):
    source_id = "medlineplus-autism"
    licence = "public-domain"
    licence_url = "https://medlineplus.gov/about/using/usingcontent/"
    attribution_template = "MedlinePlus, U.S. National Library of Medicine (public domain)"

    def __init__(
        self,
        http_client: CachedHttpClient,
        *,
        seed_path: Path | None = None,
    ) -> None:
        super().__init__(http_client)
        self._seed_path = seed_path or (DEFAULT_DATA_DIR / "seed_urls.yaml")

    def discover(self) -> Iterator[SourceItemRef]:
        for entry in _load_seed_entries(self._seed_path, _SEED_SECTION):
            yield SourceItemRef(
                source_id=self.source_id,
                item_id=str(entry["item_id"]),
                url=str(entry["url"]),
            )

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        if ref.url is None:
            raise ValueError(
                f"MedlinePlusAdapter requires ref.url for {ref.item_id!r}"
            )
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
