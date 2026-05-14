"""WHO autism adapter.

Reads a curated list of WHO autism fact-sheet URLs (HTML and/or PDF) from
`data/seed_urls.yaml`, fetches each, and emits ParsedDocument records under
CC BY-NC-SA 3.0 IGO.

The seed entries carry a `kind` field of either "html" or "pdf" that controls
which `payload_kind` is passed to `build_parsed_document`. The adapter
maintains an internal `item_id -> kind` map after `discover()` runs so that
`parse()` can dispatch correctly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar, Literal

import yaml

from autism_corpus.adapters.base import SourceAdapter, register_adapter
from autism_corpus.adapters.common import (
    build_parsed_document,
    http_get_as_raw_document,
)
from autism_corpus.config import DEFAULT_DATA_DIR
from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient

_SEED_FILE = DEFAULT_DATA_DIR / "seed_urls.yaml"
_SEED_KEY = "who-autism"

PayloadKind = Literal["html", "pdf"]


def _load_seed_entries() -> list[dict[str, Any]]:
    if not _SEED_FILE.exists():
        return []
    raw = yaml.safe_load(_SEED_FILE.read_text()) or {}
    entries = raw.get(_SEED_KEY) or []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def _coerce_kind(value: Any) -> PayloadKind:
    if value == "pdf":
        return "pdf"
    return "html"


@register_adapter
class WhoAutismAdapter(SourceAdapter):
    """Adapter for WHO autism fact sheets (HTML or PDF)."""

    source_id: ClassVar[str] = "who-autism"
    licence: ClassVar[str] = "CC-BY-NC-SA-3.0-IGO"
    licence_url: ClassVar[str] = "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"
    attribution_template: ClassVar[str] = (
        "World Health Organization, licenced under CC BY-NC-SA 3.0 IGO"
    )

    def __init__(self, http_client: CachedHttpClient) -> None:
        super().__init__(http_client)
        self._kinds: dict[str, PayloadKind] = {}

    def discover(self) -> Iterator[SourceItemRef]:
        for entry in _load_seed_entries():
            item_id = entry.get("item_id")
            url = entry.get("url")
            if not item_id or not url:
                continue
            self._kinds[item_id] = _coerce_kind(entry.get("kind"))
            yield SourceItemRef(source_id=self.source_id, item_id=item_id, url=url)

    def fetch(self, ref: SourceItemRef) -> RawDocument:
        if ref.url is None:
            raise ValueError(f"ref {ref.item_id!r} has no url")
        # Ensure kind map is populated even if fetch is called before discover.
        if ref.item_id not in self._kinds:
            for entry in _load_seed_entries():
                if entry.get("item_id") == ref.item_id:
                    self._kinds[ref.item_id] = _coerce_kind(entry.get("kind"))
                    break
        return http_get_as_raw_document(
            self.http_client,
            source_id=self.source_id,
            source_item_id=ref.item_id,
            url=ref.url,
        )

    def parse(self, raw: RawDocument) -> ParsedDocument:
        kind = self._kinds.get(raw.source_item_id, "html")
        return build_parsed_document(
            raw,
            source_id=self.source_id,
            licence=self.licence,
            licence_url=self.licence_url,
            attribution=self.attribution_template,
            content_type="fact-sheet",
            medical_disclaimer_required=False,
            payload_kind=kind,
        )
