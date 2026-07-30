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


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task02.py
# (config.py part). Only deviation: class renamed TestConfigConstants →
# TestConfigConstantsV0916 (receiver already defines TestConfigConstants).
# ═══════════════════════════════════════════════════════════════════════


class TestConfigConstantsV0916:
    """New config constants exist and have correct values."""

    def test_supported_source_extensions_exists(self):
        from kb.config import SUPPORTED_SOURCE_EXTENSIONS

        assert isinstance(SUPPORTED_SOURCE_EXTENSIONS, frozenset)
        assert ".md" in SUPPORTED_SOURCE_EXTENSIONS
        assert ".txt" in SUPPORTED_SOURCE_EXTENSIONS

    def test_valid_source_types_includes_comparison_synthesis(self):
        from kb.config import VALID_SOURCE_TYPES

        assert "comparison" in VALID_SOURCE_TYPES
        assert "synthesis" in VALID_SOURCE_TYPES
        assert "article" in VALID_SOURCE_TYPES

    def test_under_covered_type_threshold(self):
        from kb.config import UNDER_COVERED_TYPE_THRESHOLD

        assert UNDER_COVERED_TYPE_THRESHOLD == 3

    def test_stub_min_content_chars(self):
        from kb.config import STUB_MIN_CONTENT_CHARS

        assert STUB_MIN_CONTENT_CHARS == 100


# -- Cycle 90 fold from test_v5_augment_config.py --
# Verify augment config constants are present with sensible defaults and types.


def test_augment_constants_exist_with_correct_types():
    from kb import config

    assert config.AUGMENT_FETCH_MAX_BYTES == 5_000_000
    assert config.AUGMENT_FETCH_CONNECT_TIMEOUT == 5.0
    assert config.AUGMENT_FETCH_READ_TIMEOUT == 30.0
    assert config.AUGMENT_FETCH_MAX_REDIRECTS == 10
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_RUN == 10  # hard ceiling
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_HOUR == 60
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR == 3
    assert config.AUGMENT_COOLDOWN_HOURS == 24
    assert config.AUGMENT_RELEVANCE_THRESHOLD == 0.5
    assert config.AUGMENT_WIKIPEDIA_FUZZY_THRESHOLD == 0.7
    assert isinstance(config.AUGMENT_ALLOWED_DOMAINS, tuple)
    assert "en.wikipedia.org" in config.AUGMENT_ALLOWED_DOMAINS
    assert "arxiv.org" in config.AUGMENT_ALLOWED_DOMAINS
    assert isinstance(config.AUGMENT_CONTENT_TYPES, tuple)
    assert "text/html" in config.AUGMENT_CONTENT_TYPES
    assert "application/pdf" in config.AUGMENT_CONTENT_TYPES


def test_augment_allowed_domains_env_override(monkeypatch):
    monkeypatch.setenv("AUGMENT_ALLOWED_DOMAINS", "example.com,foo.org")
    # Force re-import
    import importlib

    from kb import config

    importlib.reload(config)
    try:
        assert config.AUGMENT_ALLOWED_DOMAINS == ("example.com", "foo.org")
    finally:
        # Restore default after test
        monkeypatch.delenv("AUGMENT_ALLOWED_DOMAINS")
        importlib.reload(config)


# -- Cycle 92 fold from test_v0915_task01.py (WIKI_SUBDIRS config subset) --
# ── Fix 1.7: WIKI_SUBDIRS from config ──────────────────────────


class TestWikiSubdirsFromConfig:
    """Fix 1.7 — WIKI_SUBDIRS derived from config, not hardcoded."""

    def test_pages_subdirs_match_config(self):
        from kb.config import WIKI_SUBDIR_TO_TYPE
        from kb.utils.pages import WIKI_SUBDIRS

        assert set(WIKI_SUBDIRS) == set(WIKI_SUBDIR_TO_TYPE.keys())

    def test_graph_builder_skips_files_outside_wiki_subdirs(self, tmp_path):
        """Cycle 69 AC10 — C11-L1 upgrade.

        Replaces inspect.getsource source-grep with behavioural assertion:
        build_graph only includes files inside WIKI_SUBDIRS subdirs (a
        stray top-level wiki file does NOT become a graph node).

        Mutation budget: comment out the WIKI_SUBDIRS scan filter in
        graph/builder.py -> stray top-level file becomes a node -> FAIL.
        """
        from kb.config import WIKI_SUBDIR_TO_TYPE
        from kb.graph.builder import build_graph

        wiki_dir = tmp_path / "wiki"
        # Pick a known-valid subdir (e.g., 'concepts')
        inside_subdir = next(iter(WIKI_SUBDIR_TO_TYPE.keys()))
        inside_path = wiki_dir / inside_subdir / "valid-page.md"
        inside_path.parent.mkdir(parents=True)
        inside_path.write_text(
            "---\ntitle: Valid\ntype: concept\nconfidence: stated\n---\n\n# Valid page\n",
            encoding="utf-8",
        )
        # Stray file at top level (outside WIKI_SUBDIRS)
        stray_path = wiki_dir / "stray-top-level.md"
        stray_path.write_text(
            "---\ntitle: Stray\ntype: concept\nconfidence: stated\n---\n\n# Stray\n",
            encoding="utf-8",
        )

        graph = build_graph(wiki_dir=wiki_dir)
        node_ids = set(graph.nodes())
        expected_inside = f"{inside_subdir}/valid-page"
        assert expected_inside in node_ids, (
            f"Expected {expected_inside!r} in graph nodes; got {node_ids}"
        )
        assert "stray-top-level" not in node_ids, (
            "build_graph should skip files outside WIKI_SUBDIRS subdirs"
        )

    def test_analyzer_coverage_uses_wiki_subdirs(self, tmp_path):
        """Cycle 69 AC11 — C11-L1 upgrade.

        Replaces inspect.getsource source-grep with behavioural assertion:
        analyze_coverage iterates WIKI_SUBDIRS (verified at
        ``evolve/analyzer.py:21,57``) to seed its by_type dict, so an
        empty wiki with all WIKI_SUBDIRS subdirs created reports each
        of those subdirs in under_covered_types.

        Mutation budget: hardcode a wrong subdirs literal in
        evolve/analyzer.analyze_coverage (e.g. drop one subdir) ->
        reported set != expected -> FAIL.
        """
        from kb.evolve.analyzer import analyze_coverage
        from kb.utils.pages import WIKI_SUBDIRS

        wiki_dir = tmp_path / "wiki"
        for subdir in WIKI_SUBDIRS:
            (wiki_dir / subdir).mkdir(parents=True)

        result = analyze_coverage(wiki_dir=wiki_dir)
        reported_types = set(result["under_covered_types"])
        expected_types = set(WIKI_SUBDIRS)
        assert reported_types == expected_types, (
            f"analyze_coverage reported {reported_types!r}, "
            f"expected {expected_types!r} drawn from WIKI_SUBDIRS "
            f"(used at analyzer.py:21,57)"
        )


# -- Cycle 93 fold from test_v0912_phase393.py (config constants subset) --


class TestConfigFixes:
    """config.py constants and model validation."""

    def test_max_verdicts_importable_from_config(self):
        from kb.config import MAX_VERDICTS

        assert isinstance(MAX_VERDICTS, int) and MAX_VERDICTS > 0

    def test_max_feedback_entries_importable_from_config(self):
        from kb.config import MAX_FEEDBACK_ENTRIES

        assert isinstance(MAX_FEEDBACK_ENTRIES, int) and MAX_FEEDBACK_ENTRIES > 0

    def test_empty_model_env_override_falls_back_to_default(self, monkeypatch):
        """Empty CLAUDE_SCAN_MODEL must not pass empty string to API."""
        import importlib

        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "")
        import kb.config as cfg

        importlib.reload(cfg)
        assert cfg.MODEL_TIERS["scan"] != "", "Empty env override must fall back to default"
        importlib.reload(cfg)  # restore for other tests


# -- Cycle 94 fold from test_v099_phase39.py (env-configurable model tiers) --


# ── Task 1: Environment-configurable model tiers ───────────────


class TestEnvConfigurableModelTiers:
    """Test that model tiers can be overridden via environment variables."""

    def test_default_tiers_unchanged(self):
        """Default tiers remain when no env vars set."""
        # Reimport to get fresh state
        from kb.config import MODEL_TIERS

        assert MODEL_TIERS["scan"] == "claude-haiku-4-5"
        assert MODEL_TIERS["write"] == "claude-sonnet-5"
        assert MODEL_TIERS["orchestrate"] == "claude-opus-4-8"

    def test_env_override_scan_model(self, monkeypatch):
        """CLAUDE_SCAN_MODEL env var overrides scan tier."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-haiku-model")
        # Need to reimport the module to pick up env var
        import importlib

        import kb.config

        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-haiku-model"
        finally:
            # Restore defaults
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_write_model(self, monkeypatch):
        """CLAUDE_WRITE_MODEL env var overrides write tier."""
        monkeypatch.setenv("CLAUDE_WRITE_MODEL", "custom-sonnet-model")
        import importlib

        import kb.config

        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["write"] == "custom-sonnet-model"
        finally:
            monkeypatch.delenv("CLAUDE_WRITE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_orchestrate_model(self, monkeypatch):
        """CLAUDE_ORCHESTRATE_MODEL env var overrides orchestrate tier."""
        monkeypatch.setenv("CLAUDE_ORCHESTRATE_MODEL", "custom-opus-model")
        import importlib

        import kb.config

        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["orchestrate"] == "custom-opus-model"
        finally:
            monkeypatch.delenv("CLAUDE_ORCHESTRATE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_partial_override_preserves_others(self, monkeypatch):
        """Setting one env var doesn't affect other tiers."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-scan")
        import importlib

        import kb.config

        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-scan"
            assert kb.config.MODEL_TIERS["write"] == "claude-sonnet-5"
            assert kb.config.MODEL_TIERS["orchestrate"] == "claude-opus-4-8"
        finally:
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)


# -- Cycle 94 fold from test_v09_cycle5_fixes.py (verdict validation constants export) --


def test_config_exports_verdict_validation_constants():
    from kb.config import VALID_SEVERITIES, VALID_VERDICT_TYPES

    assert VALID_SEVERITIES == ("error", "warning", "info")
    assert VALID_VERDICT_TYPES == (
        "fidelity",
        "consistency",
        "completeness",
        "review",
        "augment",
    )
