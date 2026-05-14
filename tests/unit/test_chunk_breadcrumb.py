from __future__ import annotations

from autism_corpus.chunk.breadcrumb import breadcrumb_for_offset, parse_heading_tree


class TestParseHeadingTree:
    def test_three_level_tree_in_document_order(self) -> None:
        text = (
            "# Top\n"
            "Intro\n"
            "\n"
            "## Sub A\n"
            "Body\n"
            "\n"
            "### Detail A1\n"
            "More\n"
            "\n"
            "## Sub B\n"
            "Body B\n"
        )
        tree = parse_heading_tree(text)
        # (level, heading_text, start_offset)
        assert [(lvl, h) for lvl, h, _ in tree] == [
            (1, "Top"),
            (2, "Sub A"),
            (3, "Detail A1"),
            (2, "Sub B"),
        ]
        # Offsets must be monotonically increasing.
        offsets = [off for _, _, off in tree]
        assert offsets == sorted(offsets)
        # Each offset must point at the heading line in the source text.
        for _, heading, off in tree:
            assert text[off:].startswith("#"), f"offset {off} not at # heading"
            assert heading in text[off : off + 200]

    def test_no_headings_returns_empty_list(self) -> None:
        assert parse_heading_tree("Just a paragraph of body text.\n") == []

    def test_ignores_h4_and_deeper(self) -> None:
        text = "# Top\n#### Too deep\n## Real\n"
        tree = parse_heading_tree(text)
        assert [(lvl, h) for lvl, h, _ in tree] == [(1, "Top"), (2, "Real")]


class TestBreadcrumbForOffset:
    def test_under_h1_only(self) -> None:
        text = "# Top heading\n\nSome intro text here.\n\n## Sub\n\nMore.\n"
        tree = parse_heading_tree(text)
        # Offset is inside the intro paragraph, before the H2.
        intro_offset = text.index("Some intro")
        assert (
            breadcrumb_for_offset(tree, intro_offset, site_prefix="NHS")
            == "NHS > Top heading"
        )

    def test_under_h1_h2_h3(self) -> None:
        text = (
            "# Top\n"
            "intro\n"
            "## Sub\n"
            "sub body\n"
            "### Detail\n"
            "detail body text\n"
        )
        tree = parse_heading_tree(text)
        offset = text.index("detail body")
        assert (
            breadcrumb_for_offset(tree, offset, site_prefix="NHS")
            == "NHS > Top > Sub > Detail"
        )

    def test_new_h1_resets_h2_and_h3(self) -> None:
        text = (
            "# First\n"
            "## Sub A\n"
            "### Detail A\n"
            "early body\n"
            "# Second\n"
            "later body text\n"
        )
        tree = parse_heading_tree(text)
        offset = text.index("later body")
        # Crossing into the new H1 must drop the prior H2/H3.
        assert breadcrumb_for_offset(tree, offset, site_prefix="CDC") == "CDC > Second"

    def test_plain_text_no_headings_returns_site_prefix(self) -> None:
        text = "Just a paragraph of body text.\n"
        tree = parse_heading_tree(text)
        assert breadcrumb_for_offset(tree, 5, site_prefix="NHS") == "NHS"

    def test_offset_before_first_heading_returns_site_prefix(self) -> None:
        text = "Preamble\n# Top\nbody\n"
        tree = parse_heading_tree(text)
        offset = text.index("Preamble")
        assert breadcrumb_for_offset(tree, offset, site_prefix="NHS") == "NHS"
