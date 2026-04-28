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
