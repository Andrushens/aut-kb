from __future__ import annotations

from collections.abc import Iterable

from autism_corpus.models import ParsedDocument

# Lower value = cleaner/freer licence; we prefer documents with lower priority.
_LICENCE_PRIORITY: dict[str, int] = {
    "public-domain": 0,
    "CC0-1.0": 1,
    "OGL-UK-3.0": 2,
    "CC-BY-4.0": 3,
    "CC-BY-SA-4.0": 4,
    "CC-BY-ND-4.0": 5,
    "CC-BY-NC-SA-3.0-IGO": 6,
}

# Unknown licences sort last (treated as "worst") so a known licence always
# beats an unknown one with the same hash.
_UNKNOWN_LICENCE_PRIORITY = max(_LICENCE_PRIORITY.values()) + 1


def _licence_priority(licence: str) -> int:
    return _LICENCE_PRIORITY.get(licence, _UNKNOWN_LICENCE_PRIORITY)


def deduplicate(docs: Iterable[ParsedDocument]) -> list[ParsedDocument]:
    """Group documents by ``.hash`` and keep the one with the cleanest licence
    per group.

    Ordering rules:
      * Output order tracks the position at which each distinct hash first
        appeared in *docs*.
      * Within a hash group, the kept document is the one with the lowest
        ``_LICENCE_PRIORITY`` value. Ties (same priority) are broken by
        first-seen.
    """
    # first_index: order each hash first appeared.
    first_index: dict[str, int] = {}
    # winner: the current best document for each hash.
    winner: dict[str, ParsedDocument] = {}
    winner_priority: dict[str, int] = {}

    for position, doc in enumerate(docs):
        h = doc.hash
        priority = _licence_priority(doc.licence)
        if h not in winner:
            first_index[h] = position
            winner[h] = doc
            winner_priority[h] = priority
            continue
        # Strictly lower priority wins; equal priority preserves first-seen.
        if priority < winner_priority[h]:
            winner[h] = doc
            winner_priority[h] = priority

    return [winner[h] for h in sorted(first_index, key=lambda k: first_index[k])]
