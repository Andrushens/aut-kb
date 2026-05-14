from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

import tiktoken
from syntok import segmenter
from tiktoken import Encoding

from autism_corpus.chunk.breadcrumb import breadcrumb_for_offset, parse_heading_tree
from autism_corpus.models import Chunk, ParsedDocument


@lru_cache(maxsize=4)
def _get_encoding(name: str) -> Encoding:
    return tiktoken.get_encoding(name)


@dataclass(frozen=True)
class _Section:
    start: int  # offset (inclusive) of section body in the document text
    end: int  # offset (exclusive) of section body in the document text
    breadcrumb: str  # breadcrumb for the section, with site prefix


def _segment_sections(
    text: str,
    *,
    site_prefix: str,
) -> list[_Section]:
    """Partition *text* into hard sections delimited by level-1 and level-2
    markdown headings. Each section knows its breadcrumb (which level-3
    headings nested under it may continue to refine, but ### does not start a
    new section)."""
    tree = parse_heading_tree(text)
    hard_breaks: list[int] = [0]
    for level, _heading, offset in tree:
        if level in (1, 2):
            hard_breaks.append(offset)
    hard_breaks.append(len(text))
    # Dedupe while preserving order (offset 0 may equal first heading).
    seen: set[int] = set()
    deduped: list[int] = []
    for off in hard_breaks:
        if off not in seen:
            seen.add(off)
            deduped.append(off)
    deduped.sort()

    sections: list[_Section] = []
    for start, end in pairwise(deduped):
        if start == end:
            continue
        # The breadcrumb for this section is sampled from a representative
        # offset inside it (the start works: heading offsets <= start are part
        # of the active heading stack at start).
        crumb = breadcrumb_for_offset(tree, start, site_prefix=site_prefix)
        sections.append(_Section(start=start, end=end, breadcrumb=crumb))
    return sections


def _strip_heading_line(section_text: str) -> str:
    """Remove a leading ATX heading line (#, ##) from a section body so the
    chunk body doesn't repeat the heading the breadcrumb already carries."""
    lines = section_text.split("\n", 1)
    if lines and lines[0].lstrip().startswith(("# ", "## ")):
        return lines[1] if len(lines) > 1 else ""
    return section_text


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in segmenter.analyze(text):
        for sentence in paragraph:
            rendered = "".join(tok.spacing + tok.value for tok in sentence).strip()
            if rendered:
                sentences.append(rendered)
    return sentences


def _pack_section(
    section_body: str,
    *,
    breadcrumb: str,
    target_min_tokens: int,
    target_max_tokens: int,
    overlap_tokens: int,
    enc: Encoding,
) -> list[str]:
    """Pack *section_body* into a list of chunk bodies (no breadcrumb prefix).
    Bodies aim for [target_min_tokens, target_max_tokens] tokens AFTER the
    breadcrumb prefix is added.
    """
    crumb_prefix = f"{breadcrumb}\n\n"
    crumb_tokens = len(enc.encode(crumb_prefix))
    body_min = max(1, target_min_tokens - crumb_tokens)
    body_max = max(body_min + 1, target_max_tokens - crumb_tokens)

    sentences = _split_sentences(section_body)
    if not sentences:
        return []

    # Pre-tokenise each sentence once.
    sentence_tokens: list[list[int]] = [enc.encode(s) for s in sentences]
    total_tokens = sum(len(t) for t in sentence_tokens)

    # Short section: single chunk.
    if total_tokens <= body_max:
        return [" ".join(sentences)]

    # Produce (start_index, end_index_exclusive) windows greedily, with each
    # window sized to fit [body_min, body_max] and the next window starting
    # ~overlap_tokens before the previous window's end.
    windows: list[tuple[int, int]] = []
    i = 0
    n = len(sentences)
    while i < n:
        j = i
        token_count = 0
        while j < n:
            next_len = len(sentence_tokens[j])
            if j > i and token_count + next_len > body_max:
                break
            token_count += next_len
            j += 1
            # Peek next; if adding it would exceed body_max, stop early.
            if (
                token_count >= body_min
                and j < n
                and token_count + len(sentence_tokens[j]) > body_max
            ):
                break
        windows.append((i, j))
        if j >= n:
            break
        # Walk back from j to find an earlier index whose tail of sentences
        # holds at least overlap_tokens.
        overlap_acc = 0
        back = j
        while back > i + 1 and overlap_acc < overlap_tokens:
            back -= 1
            overlap_acc += len(sentence_tokens[back])
        # Guarantee forward progress: must advance by at least one sentence.
        i = max(i + 1, back)

    # If the trailing window is below body_min, merge it into the previous one
    # so the last chunk isn't a tiny tail. This may push the merged chunk over
    # body_max; we accept a small over-shoot rather than emit a stub.
    if len(windows) >= 2:
        last_start, last_end = windows[-1]
        last_tokens = sum(len(sentence_tokens[k]) for k in range(last_start, last_end))
        if last_tokens < body_min:
            prev_start, _ = windows[-2]
            windows[-2] = (prev_start, last_end)
            windows.pop()

    bodies: list[str] = [" ".join(sentences[a:b]) for a, b in windows]
    return bodies


def chunk_document(
    doc: ParsedDocument,
    *,
    site_prefix: str,
    target_min_tokens: int = 300,
    target_max_tokens: int = 500,
    overlap_tokens: int = 50,
    tokenizer_name: str = "cl100k_base",
) -> list[Chunk]:
    """Split a :class:`ParsedDocument` into :class:`Chunk` objects.

    Rules (see Lane B spec):
      * Tokens counted with the tiktoken encoder named *tokenizer_name*.
      * Hard boundaries at level-1 and level-2 markdown headings - no chunk
        text ever spans them.
      * Each chunk's text begins with the breadcrumb on its own line, a blank
        line, then the chunk body.
      * Chunks target ``[target_min_tokens, target_max_tokens]`` tokens
        including the breadcrumb prefix.
      * Splits are sentence-aware (syntok English).
      * Adjacent chunks within the same section share ~``overlap_tokens`` of
        body overlap (overlap excludes the breadcrumb prefix).
    """
    enc = _get_encoding(tokenizer_name)
    sections = _segment_sections(doc.text, site_prefix=site_prefix)

    chunk_bodies: list[tuple[str, str]] = []  # (breadcrumb, body)
    for section in sections:
        body_text = _strip_heading_line(doc.text[section.start : section.end])
        bodies = _pack_section(
            body_text,
            breadcrumb=section.breadcrumb,
            target_min_tokens=target_min_tokens,
            target_max_tokens=target_max_tokens,
            overlap_tokens=overlap_tokens,
            enc=enc,
        )
        for body in bodies:
            chunk_bodies.append((section.breadcrumb, body))

    chunks: list[Chunk] = []
    for index, (breadcrumb, body) in enumerate(chunk_bodies):
        full_text = f"{breadcrumb}\n\n{body}"
        token_count = len(enc.encode(full_text))
        chunk_id = f"{doc.document_id}::{index:04d}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=doc.document_id,
                source_id=doc.source_id,
                canonical_url=doc.canonical_url,
                title=doc.title,
                breadcrumb=breadcrumb,
                text=full_text,
                token_count=token_count,
                language=doc.language,
                licence=doc.licence,
                attribution=doc.attribution,
                content_type=doc.content_type,
                medical_disclaimer_required=doc.medical_disclaimer_required,
                published_at=doc.published_at,
                fetched_at=doc.fetched_at,
            )
        )
    return chunks
