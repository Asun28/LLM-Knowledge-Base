"""Tests for consolidated constants (Phase 4 LOW fixes)."""
from __future__ import annotations


def test_frontmatter_re_single_source():
    from kb.compile import linker as _linker
    from kb.graph import builder as _builder
    from kb.utils import markdown as _md

    # Both modules must use the SAME regex object from utils.markdown
    assert hasattr(_md, "FRONTMATTER_RE")
    assert _builder._FRONTMATTER_RE is _md.FRONTMATTER_RE
    assert _linker._FRONTMATTER_RE is _md.FRONTMATTER_RE


def test_stopwords_single_source():
    from kb.ingest import contradiction as _contra
    from kb.query import bm25 as _bm25
    from kb.utils import text as _text

    assert hasattr(_text, "STOPWORDS")
    assert isinstance(_text.STOPWORDS, frozenset)
    # Both existing constants must alias the same object
    assert _bm25.STOP_WORDS is _text.STOPWORDS
    assert _contra._STOPWORDS is _text.STOPWORDS


def test_stopwords_union_of_both_original_sets():
    """The unified STOPWORDS must contain all words from both original sets."""
    from kb.utils.text import STOPWORDS
    # Sample words that should be in the set regardless of which file they came from
    common_words = {"the", "a", "an", "is", "are", "of", "in", "to"}
    for w in common_words:
        assert w in STOPWORDS, f"Expected '{w}' in STOPWORDS"


def test_valid_verdict_types_module_constant():
    from kb.lint import verdicts as _v

    assert hasattr(_v, "VALID_VERDICT_TYPES")
    expected = {"fidelity", "consistency", "completeness", "review", "augment"}
    assert set(_v.VALID_VERDICT_TYPES) == expected
