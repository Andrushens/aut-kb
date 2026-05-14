from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from autism_corpus.models import ParsedDocument, RawDocument, SourceItemRef
from autism_corpus.utils.http import CachedHttpClient


class SourceAdapter(ABC):
    """Base class for every source adapter.

    Subclasses set the four class attributes below and implement
    `discover/fetch/parse`. Instances take a `CachedHttpClient` so the http
    behaviour (rate limit, cache, retries, UA) is shared and configurable.

    `source_id` is the stable identifier used in chunk_ids, manifests,
    cache subdirectories, and report breakdowns. Don't change it after a
    corpus has been built — downstream services key on it.
    """

    source_id: ClassVar[str] = ""
    licence: ClassVar[str] = ""
    licence_url: ClassVar[str] = ""
    attribution_template: ClassVar[str] = ""

    def __init__(self, http_client: CachedHttpClient) -> None:
        for attr in ("source_id", "licence", "licence_url", "attribution_template"):
            if not getattr(type(self), attr, None):
                raise TypeError(
                    f"{type(self).__name__} must set class attribute {attr!r}"
                )
        self.http_client = http_client

    @abstractmethod
    def discover(self) -> Iterator[SourceItemRef]:
        """Yield references to items available from this source."""

    @abstractmethod
    def fetch(self, ref: SourceItemRef) -> RawDocument:
        """Download a single item; respects rate limits and on-disk cache."""

    @abstractmethod
    def parse(self, raw: RawDocument) -> ParsedDocument:
        """Convert a raw payload into a normalised ParsedDocument."""


_REGISTRY: dict[str, type[SourceAdapter]] = {}


def register_adapter[T: type[SourceAdapter]](cls: T) -> T:
    """Class decorator: register an adapter under its `source_id`.

    Raises ValueError if a different class is already registered for that id.
    """
    sid = cls.source_id
    if not sid:
        raise TypeError(f"{cls.__name__} must set class attribute 'source_id'")
    existing = _REGISTRY.get(sid)
    if existing is not None and existing is not cls:
        raise ValueError(f"adapter already registered for source_id={sid!r}")
    _REGISTRY[sid] = cls
    return cls


def adapter_registry() -> dict[str, type[SourceAdapter]]:
    """Return a copy of the current adapter registry."""
    return dict(_REGISTRY)
