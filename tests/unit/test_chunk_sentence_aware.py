from __future__ import annotations

import re
from datetime import UTC, date, datetime
from itertools import pairwise
from typing import Any

import pytest
import tiktoken

from autism_corpus.chunk.sentence_aware import chunk_document
from autism_corpus.models import ParsedDocument

_CHUNK_ID_RE = re.compile(r"^[^:]+(?:::[^:]+)+::(\d{4})$")


def _parsed_doc_kwargs(text: str) -> dict[str, Any]:
    return {
        "source_id": "nhs-autism",
        "source_item_id": "signs-in-toddlers",
        "canonical_url": "https://www.nhs.uk/conditions/autism/signs/children/",
        "title": "Signs of autism in young children",
        "text": text,
        "language": "en",
        "published_at": date(2023, 4, 12),
        "last_modified_at": date(2024, 1, 1),
        "licence": "OGL-UK-3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "attribution": "Information from NHS Digital, licenced under OGL v3.0",
        "content_type": "patient-info",
        "medical_disclaimer_required": False,
        "hash": "a" * 64,
        "fetched_at": datetime(2026, 5, 14, 9, 0, 0, tzinfo=UTC),
    }


_WORD_BANK = [
    "autism", "diagnosis", "clinician", "parent", "therapy", "assessment",
    "screening", "interview", "behaviour", "development", "language",
    "communication", "social", "repetitive", "sensory", "routine", "school",
    "playground", "friend", "sibling", "appointment", "paediatrician", "GP",
    "questionnaire", "observation", "milestone", "toddler", "adolescent",
    "adult", "support", "education", "service", "NHS", "council", "referral",
    "pathway", "waiting", "list", "eligibility", "neurodevelopmental",
    "coordination", "motor", "anxiety", "depression", "sleep", "mealtime",
    "transition", "strength", "interest", "passionate", "vocabulary",
    "gesture", "pointing", "imaginative", "cooperative", "empathy",
    "regulation", "meltdown", "shutdown", "stim", "hobby", "music", "painting",
    "reading", "mathematics", "computing", "engineering", "biology", "history",
    "library", "museum", "garden", "cycling", "swimming", "running", "cooking",
    "cleaning", "chores", "guideline", "NICE", "evidence", "practitioner",
    "recommendation", "appraisal", "training", "module", "workshop", "charity",
    "advocacy", "autistic-led", "research", "neurodiversity",
]


def _filler_paragraph(sentences: int, *, seed: int = 0) -> str:
    """Return a paragraph of *sentences* sentences with a wide vocabulary so
    the token-ID set is varied enough to make overlap measurements meaningful."""
    out: list[str] = []
    n_words = len(_WORD_BANK)
    for i in range(sentences):
        start = (seed + i * 11) % n_words
        # 14-word sentences keep each sentence at roughly 14-20 tokens.
        words = [_WORD_BANK[(start + j) % n_words] for j in range(14)]
        out.append(" ".join(words).capitalize() + ".")
    return " ".join(out)


@pytest.fixture
def two_section_doc() -> ParsedDocument:
    short_body = (
        "Autistic toddlers may avoid eye contact. "
        "They may not respond to their name when called. "
        "Some children prefer to play alone rather than with peers. "
        "Repetitive movements are common in this age group. "
        "These signs vary in intensity from child to child."
    )
    long_body = _filler_paragraph(80, seed=3)
    text = (
        "# Signs of autism\n"
        "\n"
        "## Section 1\n"
        "\n"
        f"{short_body}\n"
        "\n"
        "## Section 2\n"
        "\n"
        f"{long_body}\n"
    )
    return ParsedDocument(**_parsed_doc_kwargs(text))


class TestChunkDocument:
    def test_short_section_produces_one_chunk(self, two_section_doc: ParsedDocument) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        section1_chunks = [c for c in chunks if "Section 1" in c.breadcrumb]
        assert len(section1_chunks) == 1

    def test_long_section_produces_multiple_chunks(
        self, two_section_doc: ParsedDocument
    ) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        section2_chunks = [c for c in chunks if "Section 2" in c.breadcrumb]
        assert len(section2_chunks) >= 2

    def test_no_chunk_crosses_section_boundary(
        self, two_section_doc: ParsedDocument
    ) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        for chunk in chunks:
            assert not (
                "## Section 1" in chunk.text and "## Section 2" in chunk.text
            ), f"Chunk {chunk.chunk_id} crossed a section boundary"

    def test_every_chunk_text_starts_with_breadcrumb_line(
        self, two_section_doc: ParsedDocument
    ) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        for chunk in chunks:
            first_line = chunk.text.split("\n", 1)[0]
            assert first_line == chunk.breadcrumb, (
                f"chunk {chunk.chunk_id} starts with {first_line!r}, "
                f"not breadcrumb {chunk.breadcrumb!r}"
            )

    def test_token_counts_within_target_band(self, two_section_doc: ParsedDocument) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        long_chunks = [c for c in chunks if "Section 2" in c.breadcrumb]
        for chunk in long_chunks:
            assert 250 <= chunk.token_count <= 550, (
                f"chunk {chunk.chunk_id} has token_count {chunk.token_count}, "
                "outside [250, 550]"
            )

    def test_chunk_ids_monotonic_zero_padded(self, two_section_doc: ParsedDocument) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        indices: list[int] = []
        for chunk in chunks:
            assert chunk.chunk_id.startswith(chunk.document_id + "::")
            m = _CHUNK_ID_RE.match(chunk.chunk_id)
            assert m is not None, f"chunk_id {chunk.chunk_id!r} does not match pattern"
            indices.append(int(m.group(1)))
        assert indices == list(range(len(indices)))
        assert indices[0] == 0
        # zero-padded width = 4
        assert all(chunk.chunk_id.split("::")[-1] == f"{i:04d}" for i, chunk in enumerate(chunks))

    def test_overlap_between_adjacent_chunks_in_same_section(
        self, two_section_doc: ParsedDocument
    ) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        section2_chunks = [c for c in chunks if "Section 2" in c.breadcrumb]
        assert len(section2_chunks) >= 2

        enc = tiktoken.get_encoding("cl100k_base")
        for prev, curr in pairwise(section2_chunks):
            # Strip the breadcrumb prefix line + blank line from the body.
            prev_body = prev.text.split("\n\n", 1)[1]
            curr_body = curr.text.split("\n\n", 1)[1]
            prev_tail = enc.encode(prev_body)[-80:]
            curr_head = enc.encode(curr_body)[:80]
            overlap = len(set(prev_tail) & set(curr_head))
            assert 30 <= overlap <= 80, (
                f"overlap between {prev.chunk_id} and {curr.chunk_id} = {overlap}, "
                "expected 30..80"
            )

    def test_doc_metadata_propagated_to_chunks(self, two_section_doc: ParsedDocument) -> None:
        chunks = chunk_document(two_section_doc, site_prefix="NHS")
        assert chunks, "expected at least one chunk"
        for chunk in chunks:
            assert chunk.licence == two_section_doc.licence
            assert chunk.attribution == two_section_doc.attribution
            assert chunk.title == two_section_doc.title
            assert chunk.language == two_section_doc.language
            assert chunk.content_type == two_section_doc.content_type
            assert chunk.canonical_url == two_section_doc.canonical_url
            assert chunk.source_id == two_section_doc.source_id
            assert chunk.document_id == two_section_doc.document_id
            assert chunk.fetched_at == two_section_doc.fetched_at
            assert chunk.published_at == two_section_doc.published_at
            assert (
                chunk.medical_disclaimer_required
                == two_section_doc.medical_disclaimer_required
            )

    def test_plain_text_no_headings_uses_site_prefix_breadcrumb(self) -> None:
        text = _filler_paragraph(8, seed=1) + "\n"
        doc = ParsedDocument(**_parsed_doc_kwargs(text))
        chunks = chunk_document(doc, site_prefix="NHS")
        assert chunks
        for chunk in chunks:
            assert chunk.breadcrumb == "NHS"
            assert chunk.text.startswith("NHS\n\n")
