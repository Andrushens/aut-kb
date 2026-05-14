from __future__ import annotations

import pytest

from autism_corpus.normalize.text import detect_language, normalize_whitespace


class TestNormalizeWhitespace:
    def test_collapses_runs_of_spaces(self) -> None:
        assert normalize_whitespace("hello    world") == "hello world"

    def test_collapses_tabs_and_spaces_together(self) -> None:
        assert normalize_whitespace("hello \t  \t world") == "hello world"

    def test_strips_trailing_whitespace_per_line(self) -> None:
        assert normalize_whitespace("line one   \nline two\t\n") == "line one\nline two"

    def test_collapses_four_newlines_to_two(self) -> None:
        assert normalize_whitespace("para1\n\n\n\npara2") == "para1\n\npara2"

    def test_collapses_three_newlines_to_two(self) -> None:
        assert normalize_whitespace("para1\n\n\npara2") == "para1\n\npara2"

    def test_preserves_single_and_double_newlines(self) -> None:
        assert normalize_whitespace("a\nb\n\nc") == "a\nb\n\nc"

    def test_strips_surrounding_whitespace(self) -> None:
        assert normalize_whitespace("\n\n  hello world  \n\n") == "hello world"

    def test_empty_string(self) -> None:
        assert normalize_whitespace("") == ""


class TestDetectLanguage:
    def test_detects_english(self) -> None:
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a test sentence about autism."
        )
        assert detect_language(text) == "en"

    def test_empty_string_returns_und(self) -> None:
        assert detect_language("") == "und"

    def test_detects_arabic(self) -> None:
        # "Autism is a developmental disorder that affects communication and behavior."
        arabic = "التوحد هو اضطراب في النمو يؤثر على التواصل والسلوك لدى الأطفال."
        assert detect_language(arabic) == "ar"

    @pytest.mark.parametrize(
        "junk",
        ["   ", "\n\n\t", "...", "123 456 789"],
    )
    def test_low_signal_inputs_return_und(self, junk: str) -> None:
        assert detect_language(junk) == "und"
