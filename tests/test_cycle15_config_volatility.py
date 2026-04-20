"""Cycle 15 AC14/AC15/AC16/AC3-constant regression tests.

Covers:
  - SOURCE_VOLATILITY_TOPICS is a frozen, case-folded mapping (AC14).
  - volatility_multiplier_for word-boundary + length-cap semantics (AC15, T1).
  - decay_days_for(topics=...) composes with multiplier; NaN/inf/zero/negative
    fall back to 1.0 BEFORE int(); result clamped to [1, DEFAULT*50] (AC16, T2).
  - AUTHORED_BY_BOOST constant present (AC3 config half).
"""

from __future__ import annotations

import math
import time

import pytest

from kb import config
from kb.config import (
    AUTHORED_BY_BOOST,
    SOURCE_DECAY_DEFAULT_DAYS,
    SOURCE_VOLATILITY_TOPICS,
    decay_days_for,
    volatility_multiplier_for,
)

# ─── AC3 constant half ────────────────────────────────────────────────────


def test_authored_by_boost_constant():
    """AC3 — AUTHORED_BY_BOOST exists at the expected magnitude."""
    assert AUTHORED_BY_BOOST == 0.02


# ─── AC14 SOURCE_VOLATILITY_TOPICS shape ─────────────────────────────────


def test_volatility_topics_is_mapping():
    """AC14 — SOURCE_VOLATILITY_TOPICS is a Mapping."""
    from collections.abc import Mapping

    assert isinstance(SOURCE_VOLATILITY_TOPICS, Mapping)


def test_volatility_topics_is_read_only():
    """AC14 — MappingProxyType prevents caller mutation."""
    with pytest.raises(TypeError):
        SOURCE_VOLATILITY_TOPICS["new_topic"] = 2.0  # type: ignore[index]


def test_volatility_topics_casefolded_at_definition():
    """AC14 — keys are casefolded so lookups don't need to worry about case."""
    # All shipped keys are already lowercase ASCII, but the transformation
    # pipeline must run so future non-ASCII additions are normalised.
    assert "llm" in SOURCE_VOLATILITY_TOPICS
    assert "react" in SOURCE_VOLATILITY_TOPICS
    assert "docker" in SOURCE_VOLATILITY_TOPICS


def test_volatility_topics_values_are_floats():
    """AC14 — values are floats; at least one >1.0."""
    for v in SOURCE_VOLATILITY_TOPICS.values():
        assert isinstance(v, float)
    assert max(SOURCE_VOLATILITY_TOPICS.values()) > 1.0


# ─── AC15 volatility_multiplier_for ───────────────────────────────────────


def test_volatility_multiplier_for_none_returns_one():
    """AC15 — None input returns 1.0 (no multiplier)."""
    assert volatility_multiplier_for(None) == 1.0


def test_volatility_multiplier_for_empty_returns_one():
    """AC15 — empty string returns 1.0."""
    assert volatility_multiplier_for("") == 1.0


def test_volatility_multiplier_for_case_insensitive():
    """AC15 — `LLM` matches the lowercase `llm` key."""
    assert volatility_multiplier_for("LLM agents") > 1.0


def test_volatility_multiplier_for_no_match_returns_one():
    """AC15 — text without any keyword returns 1.0."""
    assert volatility_multiplier_for("rust systems programming") == 1.0


def test_volatility_multiplier_for_word_boundary():
    """AC15/T1 — `reactor` does NOT fire the `react` key (boundary enforcement)."""
    # Ensure we don't get false positives on substrings containing the keyword.
    assert volatility_multiplier_for("nuclear reactor safety") == 1.0


def test_volatility_multiplier_for_hyphen_is_boundary():
    """AC15 — `react-native` DOES fire because `-` is a word boundary."""
    assert volatility_multiplier_for("react-native development") > 1.0


def test_volatility_multiplier_for_max_across_keys():
    """AC15 — text matching multiple keys returns the max multiplier."""
    # Both `llm` and `docker` ship at 1.1 today; max is 1.1.
    assert volatility_multiplier_for("llm docker") == 1.1


def test_volatility_multiplier_for_length_cap_fast():
    """AC15/T1 — 10M-char input truncated to 4096; returns <200ms, returns 1.0."""
    huge = "a" * 10_000_000
    t0 = time.monotonic()
    result = volatility_multiplier_for(huge)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.2, f"volatility regex took {elapsed:.3f}s on 10M input"
    # Input is all `a`s so no keyword matches; expect 1.0 after truncation.
    assert result == 1.0


# ─── AC16 decay_days_for(topics=...) ──────────────────────────────────────


def test_decay_days_for_topics_none_backward_compat():
    """AC16 — topics=None (default) preserves pre-cycle-15 behaviour."""
    assert decay_days_for("https://arxiv.org/abs/X") == 1095
    assert decay_days_for("https://arxiv.org/abs/X", topics=None) == 1095


def test_decay_days_for_topics_applies_multiplier():
    """AC16 — topics matching an LLM keyword extends decay by 1.1×."""
    # arxiv base 1095d × 1.1 = 1204
    assert decay_days_for("https://arxiv.org/abs/X", topics="LLM agents") == 1204


def test_decay_days_for_topics_no_match_no_change():
    """AC16 — topics without keyword match returns base_days unchanged."""
    assert decay_days_for("https://arxiv.org/abs/X", topics="rust systems") == 1095


def test_decay_days_for_topics_nan_fallback(monkeypatch):
    """AC16/T2 — NaN multiplier falls back to 1.0 (no ValueError)."""
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: float("nan"))
    # Should NOT raise ValueError: cannot convert float NaN to integer
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == 1095  # fallback to 1.0 × 1095 base


def test_decay_days_for_topics_inf_fallback(monkeypatch):
    """AC16/T2 — infinity multiplier falls back to 1.0."""
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: math.inf)
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == 1095


def test_decay_days_for_topics_zero_fallback(monkeypatch):
    """AC16/T2 — zero multiplier falls back to 1.0."""
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: 0.0)
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == 1095


def test_decay_days_for_topics_negative_fallback(monkeypatch):
    """AC16/T2 — negative multiplier falls back to 1.0."""
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: -1.5)
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == 1095


def test_decay_days_for_topics_clamp_ceiling(monkeypatch):
    """AC16/T2 — hostile large multiplier clamped to DEFAULT*50 = 4500."""
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: 1e10)
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == SOURCE_DECAY_DEFAULT_DAYS * 50  # 90 * 50 = 4500


def test_decay_days_for_topics_clamp_floor(monkeypatch):
    """AC16/T2 — tiny positive multiplier clamped to min 1 day."""
    # 1e-10 * 1095 = 1.095e-7 → int() = 0 → clamp to 1.
    monkeypatch.setattr(config, "volatility_multiplier_for", lambda t: 1e-10)
    result = decay_days_for("https://arxiv.org/abs/X", topics="anything")
    assert result == 1


def test_decay_days_for_no_ref_with_topics():
    """AC16 — no ref still returns SOURCE_DECAY_DEFAULT_DAYS as base, multiplied."""
    # 90 (default) * 1.1 = 99
    assert decay_days_for(None, topics="LLM") == 99
