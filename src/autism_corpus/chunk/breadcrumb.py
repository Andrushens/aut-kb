from __future__ import annotations

import re

# Match a level-1, -2, or -3 ATX-style markdown heading at the start of a line.
# Allow trailing whitespace; capture the level (count of #) and the heading text.
_HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def parse_heading_tree(markdown_text: str) -> list[tuple[int, str, int]]:
    """Return ``(level, heading_text, start_offset)`` for every #, ##, or ###
    heading in *markdown_text*, in document order.

    Levels 4+ are ignored. ``start_offset`` is the byte offset of the leading
    ``#`` in the source text.
    """
    tree: list[tuple[int, str, int]] = []
    for match in _HEADING_RE.finditer(markdown_text):
        hashes = match.group(1)
        # Defensive: regex restricts to 1-3, but assert intent for readers.
        if not 1 <= len(hashes) <= 3:
            continue
        level = len(hashes)
        heading = match.group(2).strip()
        if not heading:
            continue
        tree.append((level, heading, match.start()))
    return tree


def breadcrumb_for_offset(
    tree: list[tuple[int, str, int]],
    offset: int,
    *,
    site_prefix: str,
) -> str:
    """Return ``"{site_prefix} > H1 > H2 > H3"`` for the heading path active at
    *offset*.

    The heading path is built by scanning all headings whose ``start_offset`` is
    ``<= offset`` and tracking the most recent heading per level, with deeper
    levels reset whenever a shallower heading appears.
    """
    current: dict[int, str] = {}
    for level, heading, start in tree:
        if start > offset:
            break
        current[level] = heading
        # Any heading resets all deeper levels.
        for deeper in (lvl for lvl in list(current) if lvl > level):
            del current[deeper]

    parts: list[str] = [site_prefix]
    for level in (1, 2, 3):
        if level in current:
            parts.append(current[level])
    return " > ".join(parts)
