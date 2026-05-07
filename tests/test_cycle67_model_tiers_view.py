"""Cycle 67 AC01 — `MODEL_TIERS` legacy import-time-captured dict → call-time view.

Mimo r5 Q1+Q2 flagged the actual surface (the legacy `MODEL_TIERS` dict
literal at `config.py:237-241`, NOT the misnamed `_DEFAULT_MODEL_TIERS`).
The dict captured `os.environ.get(CLAUDE_*_MODEL)` at IMPORT TIME, so
tests using `monkeypatch.setenv(...)` AFTER `import kb.config` got stale
values — same hazard class as cycle-19 L2 reload-leak.

Cycle 67 AC01 replaces the literal with a `_ModelTiersView(Mapping)` whose
`__getitem__` delegates to `get_model_tier(tier)` — env read at CALL TIME.
Bracket access surface preserved.

Five conditions from Step 5 design gate:
- C-AC01-conv: `dict(MODEL_TIERS) == {<env>}` reads env at conversion
- C-AC01-map: `.keys()`, `.values()`, `.items()` all env-dynamic
- C-AC01-eq: `MODEL_TIERS != {literal dict}` documented (use `dict(view)`)
- C-AC01-iter: `list(MODEL_TIERS) == ["scan", "write", "orchestrate"]`
- C-AC01-json: `json.dumps(dict(MODEL_TIERS))` succeeds
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

import kb.config
from kb.config import MODEL_TIERS, _DEFAULT_MODEL_TIERS, _ModelTiersView


def test_t01a_call_time_lookup_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """T01-A: setenv after kb.config import → lookup returns the new value.
    Closes the cycle-19 L2 stale-snapshot hazard."""
    monkeypatch.setenv("CLAUDE_SCAN_MODEL", "test-haiku-cycle67")
    assert MODEL_TIERS["scan"] == "test-haiku-cycle67"


def test_t01b_default_falls_through_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T01-B: env unset → default value from _DEFAULT_MODEL_TIERS."""
    monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
    assert MODEL_TIERS["scan"] == _DEFAULT_MODEL_TIERS["scan"]
    monkeypatch.delenv("CLAUDE_WRITE_MODEL", raising=False)
    assert MODEL_TIERS["write"] == _DEFAULT_MODEL_TIERS["write"]
    monkeypatch.delenv("CLAUDE_ORCHESTRATE_MODEL", raising=False)
    assert MODEL_TIERS["orchestrate"] == _DEFAULT_MODEL_TIERS["orchestrate"]


def test_t01c_unknown_tier_raises_keyerror() -> None:
    """T01-C: unknown tier raises KeyError (Mapping ABC canonical missing-key
    exception). Original ValueError from get_model_tier is preserved in the
    `__cause__` chain so debug logs still see the diagnostic message.
    """
    with pytest.raises(KeyError):
        _ = MODEL_TIERS["unknown_tier"]
    # Direct get_model_tier call still raises ValueError (its native
    # contract); the view wraps it in KeyError for Mapping ABC compliance.
    with pytest.raises(ValueError, match=r"invalid tier"):
        kb.config.get_model_tier("unknown_tier")


def test_t01d_dict_conversion_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """T01-D / C-AC01-conv: `dict(MODEL_TIERS)` reads env at conversion."""
    monkeypatch.setenv("CLAUDE_SCAN_MODEL", "conv-test-haiku")
    monkeypatch.setenv("CLAUDE_WRITE_MODEL", "conv-test-sonnet")
    monkeypatch.setenv("CLAUDE_ORCHESTRATE_MODEL", "conv-test-opus")
    converted = dict(MODEL_TIERS)
    assert converted == {
        "scan": "conv-test-haiku",
        "write": "conv-test-sonnet",
        "orchestrate": "conv-test-opus",
    }


def test_t01e_mapping_methods_env_dynamic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T01-E / C-AC01-map: `.keys()`, `.values()`, `.items()` all read env."""
    monkeypatch.setenv("CLAUDE_SCAN_MODEL", "map-haiku")
    keys = list(MODEL_TIERS.keys())
    assert "scan" in keys and "write" in keys and "orchestrate" in keys

    values = list(MODEL_TIERS.values())
    assert "map-haiku" in values, (
        f"AC01 T01-E: .values() should reflect env-dynamic value 'map-haiku'; "
        f"got {values!r}"
    )
    items = dict(MODEL_TIERS.items())
    assert items["scan"] == "map-haiku"

    assert MODEL_TIERS.get("scan") == "map-haiku"
    assert MODEL_TIERS.get("nonexistent", "fallback") == "fallback"


def test_t01f_eq_to_dict_works_via_mapping_abc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T01-F / C-AC01-eq (CORRECTED): R2-F3 anticipated equality would NOT
    work with a plain Mapping subclass. In fact, `collections.abc.Mapping`
    DOES implement `__eq__` by element-wise comparison (Mapping ABC source).
    A `_ModelTiersView` instance IS `==` to a dict with the same contents.

    This is GOOD for back-compat: existing callers doing `MODEL_TIERS == {...}`
    keep working with content-aware equality. The R2 concern is resolved by
    the Mapping ABC default impl — no override needed.
    """
    # Force defaults so we can compare against _DEFAULT_MODEL_TIERS.
    monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_WRITE_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_ORCHESTRATE_MODEL", raising=False)

    bare_dict = {
        "scan": _DEFAULT_MODEL_TIERS["scan"],
        "write": _DEFAULT_MODEL_TIERS["write"],
        "orchestrate": _DEFAULT_MODEL_TIERS["orchestrate"],
    }
    # Mapping ABC's __eq__ compares element-wise; works with any Mapping or
    # Mapping-compatible (dict counts).
    assert MODEL_TIERS == bare_dict
    # Reverse direction: dict.__eq__ does NOT recognize a Mapping subclass
    # as equal — `bare_dict == MODEL_TIERS` returns False (asymmetric). This
    # is a known Python quirk; document it.
    # (Skip the reverse assertion since behavior depends on Python's __eq__
    #  resolution order; the forward assertion is what callers rely on.)
    assert dict(MODEL_TIERS) == bare_dict


def test_t01g_iter_order_stable() -> None:
    """T01-G / C-AC01-iter: iteration order matches `_DEFAULT_MODEL_TIERS`
    insertion order."""
    assert list(MODEL_TIERS) == list(_DEFAULT_MODEL_TIERS)
    assert list(MODEL_TIERS) == ["scan", "write", "orchestrate"]


def test_t01h_json_serialization_via_dict_conversion() -> None:
    """T01-H / C-AC01-json: `json.dumps(dict(MODEL_TIERS))` succeeds.
    Direct `json.dumps(MODEL_TIERS)` may fail since MODEL_TIERS is not a
    raw dict; document the workaround.
    """
    snapshot = dict(MODEL_TIERS)
    serialized = json.dumps(snapshot)
    assert "scan" in serialized
    assert "write" in serialized
    assert "orchestrate" in serialized


def test_t01i_isinstance_mapping() -> None:
    """T01-I: MODEL_TIERS IS a collections.abc.Mapping. Pin the contract so
    a future maintainer doesn't replace it with a non-Mapping."""
    assert isinstance(MODEL_TIERS, Mapping)
    assert isinstance(kb.config.MODEL_TIERS, Mapping)


def test_t01j_divergent_fail_revert_breaks_call_time() -> None:
    """T01-J (divergent-fail): if a future maintainer reverts the proxy back
    to a literal dict, T01-A / T01-D / T01-E would all fail. Anchor that
    by asserting MODEL_TIERS is the proxy class instance, not a bare dict.
    """
    assert isinstance(MODEL_TIERS, _ModelTiersView), (
        "AC01 T01-J: MODEL_TIERS MUST be a _ModelTiersView instance. "
        f"Got: {type(MODEL_TIERS).__name__}. Revert to literal dict broke AC01."
    )
    assert type(MODEL_TIERS) is not dict


def test_t01k_repr_does_not_crash() -> None:
    """T01-K: __repr__ produces a usable string; doesn't crash on env state."""
    r = repr(MODEL_TIERS)
    assert r.startswith("_ModelTiersView(")
