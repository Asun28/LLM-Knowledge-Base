"""Tests for kb.config constants — values, types, immutability.

Cycle 47 fold receiver: TestConfigConstants from cycle 16
(test_cycle16_config_constants.py, fold per Phase 4.5 HIGH #4 freeze-and-fold
rule + Step-5 design Q1 — new test_config.py file rather than splitting
constants between test_lint.py + test_query.py).
"""

import pytest

from kb import config


class TestConfigConstants:
    # ── Cycle 16 AC1-AC3 — config constants for query refinement + lint quality ─

    def test_query_rephrasing_max_is_int_three(self) -> None:
        """AC1 — QUERY_REPHRASING_MAX == 3, typed int."""
        assert isinstance(config.QUERY_REPHRASING_MAX, int)
        assert config.QUERY_REPHRASING_MAX == 3

    def test_duplicate_slug_distance_threshold_is_int_three(self) -> None:
        """AC2 — DUPLICATE_SLUG_DISTANCE_THRESHOLD == 3, typed int."""
        assert isinstance(config.DUPLICATE_SLUG_DISTANCE_THRESHOLD, int)
        assert config.DUPLICATE_SLUG_DISTANCE_THRESHOLD == 3

    def test_callout_markers_is_tuple_of_four_strings(self) -> None:
        """AC3 — CALLOUT_MARKERS is a tuple of the 4 canonical marker names."""
        assert isinstance(config.CALLOUT_MARKERS, tuple)
        assert config.CALLOUT_MARKERS == ("contradiction", "gap", "stale", "key-insight")

    def test_callout_markers_tuple_is_immutable(self) -> None:
        """AC3 — CALLOUT_MARKERS uses tuple semantics (no index assignment)."""
        with pytest.raises(TypeError):
            config.CALLOUT_MARKERS[0] = "other"  # type: ignore[index]

    def test_callout_markers_entries_are_plain_lowercase(self) -> None:
        """AC3 — each marker is a lowercase ASCII string (safe for regex + render)."""
        for marker in config.CALLOUT_MARKERS:
            assert isinstance(marker, str)
            assert marker == marker.lower()
            assert marker.replace("-", "").isalpha()

    # ── Cycle 69 AC18 — folded from test_v01002_consolidated_constants.py ─

    def test_frontmatter_re_single_source(self):
        from kb.compile import linker as _linker
        from kb.graph import builder as _builder
        from kb.utils import markdown as _md

        # Both modules must use the SAME regex object from utils.markdown
        assert hasattr(_md, "FRONTMATTER_RE")
        assert _builder._FRONTMATTER_RE is _md.FRONTMATTER_RE
        assert _linker._FRONTMATTER_RE is _md.FRONTMATTER_RE

    def test_stopwords_single_source(self):
        from kb.ingest import contradiction as _contra
        from kb.query import bm25 as _bm25
        from kb.utils import text as _text

        assert hasattr(_text, "STOPWORDS")
        assert isinstance(_text.STOPWORDS, frozenset)
        # Both existing constants must alias the same object
        assert _bm25.STOP_WORDS is _text.STOPWORDS
        assert _contra._STOPWORDS is _text.STOPWORDS

    def test_stopwords_union_of_both_original_sets(self):
        """The unified STOPWORDS must contain all words from both original sets."""
        from kb.utils.text import STOPWORDS

        # Sample words that should be in the set regardless of which file they came from
        common_words = {"the", "a", "an", "is", "are", "of", "in", "to"}
        for w in common_words:
            assert w in STOPWORDS, f"Expected '{w}' in STOPWORDS"

    def test_valid_verdict_types_module_constant(self):
        from kb.lint import verdicts as _v

        assert hasattr(_v, "VALID_VERDICT_TYPES")
        expected = {"fidelity", "consistency", "completeness", "review", "augment"}
        assert set(_v.VALID_VERDICT_TYPES) == expected
