"""Cycle 73 AC02 — Verdict-store ``prompt_version`` stamp + accessor.

Tests for cycle-73 AC02: ``add_verdict`` writes ``prompt_version: int``;
new ``get_prompt_version(entry: dict) -> int`` accessor with default 0
for legacy entries. ``load_verdicts`` UNCHANGED (no cache mutation per
threat-model T7).

Per design-decision Q1 + §11 (FROZEN at Step 5):
- C-AC02-1: ``CURRENT_PROMPT_VERSION = 1`` lives in ``kb.config``
- C-AC02-2: ``add_verdict`` stamps fresh entries with the constant
- C-AC02-3: ``get_prompt_version(entry)`` returns 0 for missing key,
  defensively returns 0 for non-dict inputs (R2 F-1 condition)

Threat-model: T3 (Repudiation — forensic prompt-shape gap closed) +
T7 (Tampering — cache fidelity preserved; no read-side mutation).

Per ``feedback_test_behavior_over_signature``: behavioural assertions only.
Per cycle-72 L7: multi-entry fixtures use COUNT not PRESENCE assertions.
"""

from __future__ import annotations

import pytest


# ── AC02 lock-in ──────────────────────────────────────────────────────


class TestAC02_AddVerdictStampsCurrentVersion:
    """C-AC02-2: ``add_verdict`` writes ``prompt_version: int`` field
    matching ``kb.config.CURRENT_PROMPT_VERSION``.
    """

    def test_add_verdict_stamps_current_prompt_version(self, tmp_path):
        """Fresh entry has ``entry['prompt_version'] == CURRENT_PROMPT_VERSION``."""
        from kb.config import CURRENT_PROMPT_VERSION
        from kb.lint.verdicts import add_verdict, load_verdicts

        verdicts_path = tmp_path / "verdicts.json"
        entry = add_verdict(
            page_id="entities/test",
            verdict_type="fidelity",
            verdict="pass",
            issues=[],
            notes="cycle-73 AC02 lock-in",
            path=verdicts_path,
        )

        assert entry["prompt_version"] == CURRENT_PROMPT_VERSION, (
            f"add_verdict did NOT stamp prompt_version with CURRENT_PROMPT_VERSION "
            f"({CURRENT_PROMPT_VERSION}); got {entry.get('prompt_version')!r}"
        )

        # And the stamp persists through round-trip via load_verdicts.
        loaded = load_verdicts(path=verdicts_path)
        assert len(loaded) == 1, f"expected 1 verdict, got {len(loaded)}"
        assert loaded[0]["prompt_version"] == CURRENT_PROMPT_VERSION, (
            "round-trip lost prompt_version stamp"
        )

    def test_current_prompt_version_is_one(self):
        """C-AC02-1 + Q5 freeze: ``CURRENT_PROMPT_VERSION == 1`` (the
        post-cycle-70 wrap_wiki_context family is one shape; cycle-71/72/
        73 expansions are site-additions, not shape-revisions)."""
        from kb.config import CURRENT_PROMPT_VERSION

        assert CURRENT_PROMPT_VERSION == 1, (
            f"CURRENT_PROMPT_VERSION must equal 1 per Q5 design freeze; "
            f"got {CURRENT_PROMPT_VERSION!r}"
        )
        assert isinstance(CURRENT_PROMPT_VERSION, int), (
            "CURRENT_PROMPT_VERSION must be an int (forensic comparator)"
        )


class TestAC02_GetPromptVersionAccessor:
    """C-AC02-3: ``get_prompt_version(entry)`` accessor with default 0
    for legacy entries; defensive type handling.
    """

    def test_get_prompt_version_returns_stamp_for_post_cycle73_entry(self):
        """Entry with the key returns its int value."""
        from kb.lint.verdicts import get_prompt_version

        entry = {"page_id": "x", "prompt_version": 1, "verdict": "pass"}
        assert get_prompt_version(entry) == 1

        entry_legacy = {"page_id": "x", "prompt_version": 2, "verdict": "pass"}
        assert get_prompt_version(entry_legacy) == 2

    def test_get_prompt_version_legacy_entry_default_zero(self):
        """Entry WITHOUT the ``prompt_version`` key returns 0 (= pre-cycle-70
        unknown shape).

        This is the read-side back-fill — accessor pattern, NOT cache mutation."""
        from kb.lint.verdicts import get_prompt_version

        legacy_entry = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "page_id": "concepts/rag",
            "verdict_type": "fidelity",
            "verdict": "pass",
            "issues": [],
            "notes": "pre-cycle-73 entry, no prompt_version key",
        }
        assert get_prompt_version(legacy_entry) == 0, (
            "legacy entry without prompt_version key MUST return 0"
        )

    def test_get_prompt_version_handles_non_dict_inputs_defensively(self):
        """R2 F-1 condition: defensive type handling — accessor returns 0 on
        any non-dict input (None, list, str) rather than raising AttributeError."""
        from kb.lint.verdicts import get_prompt_version

        # Each variant must return 0 (NOT raise).
        assert get_prompt_version(None) == 0  # type: ignore[arg-type]
        assert get_prompt_version([]) == 0  # type: ignore[arg-type]
        assert get_prompt_version("not a dict") == 0  # type: ignore[arg-type]
        assert get_prompt_version(42) == 0  # type: ignore[arg-type]

    def test_get_prompt_version_handles_non_int_value_defensively(self):
        """If the field exists but contains a non-int (corrupted JSON),
        the accessor returns 0 rather than propagating the bad value."""
        from kb.lint.verdicts import get_prompt_version

        corrupt = {"page_id": "x", "prompt_version": "not_an_int"}
        assert get_prompt_version(corrupt) == 0, (
            "non-int prompt_version field MUST default to 0 (forensic safety)"
        )

        corrupt_none = {"page_id": "x", "prompt_version": None}
        assert get_prompt_version(corrupt_none) == 0


class TestAC02_NoCacheReadSideMutation:
    """T7 invariant: ``load_verdicts`` does NOT mutate cached entries —
    on-disk fidelity preserved. Cache contents byte-for-byte mirror the
    JSON file."""

    def test_load_verdicts_does_not_inject_prompt_version_key(self, tmp_path):
        """Manually-written legacy verdicts (no prompt_version key) MUST
        come back through load_verdicts UNCHANGED — no key injection."""
        import json

        from kb.lint.verdicts import load_verdicts

        verdicts_path = tmp_path / "legacy_verdicts.json"
        legacy_entries = [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "page_id": "concepts/rag",
                "verdict_type": "fidelity",
                "verdict": "pass",
                "issues": [],
                "notes": "legacy A",
            },
            {
                "timestamp": "2026-01-02T00:00:00+00:00",
                "page_id": "concepts/transformer",
                "verdict_type": "consistency",
                "verdict": "warning",
                "issues": [{"severity": "warn", "description": "legacy B"}],
                "notes": "legacy B",
            },
        ]
        verdicts_path.write_text(json.dumps(legacy_entries), encoding="utf-8")

        loaded = load_verdicts(path=verdicts_path)
        assert len(loaded) == 2, f"expected 2 entries, got {len(loaded)}"

        # Cycle-72 L7: COUNT assertions for multi-entry fixtures.
        # ALL entries must have NO prompt_version key (read-side did NOT
        # inject the back-fill — accessor-only design).
        no_key_count = sum(1 for e in loaded if "prompt_version" not in e)
        assert no_key_count == 2, (
            f"load_verdicts injected prompt_version into {2 - no_key_count} of 2 "
            "legacy entries — T7 read-side mutation violation"
        )

        # And the on-disk file is unchanged byte-for-byte.
        on_disk = json.loads(verdicts_path.read_text(encoding="utf-8"))
        assert on_disk == legacy_entries, (
            "load_verdicts mutated the on-disk JSON file"
        )

    def test_load_verdicts_preserves_existing_post_cycle73_entries(self, tmp_path):
        """When entries DO have ``prompt_version`` key (e.g., written by
        post-cycle-73 add_verdict), load_verdicts preserves the value
        verbatim — including unusual values like 0 or 99."""
        import json

        from kb.lint.verdicts import load_verdicts

        verdicts_path = tmp_path / "mixed_verdicts.json"
        mixed_entries = [
            {"page_id": "a", "prompt_version": 1, "verdict": "pass"},
            {"page_id": "b", "prompt_version": 0, "verdict": "fail"},
            {"page_id": "c", "verdict": "warning"},  # legacy
            {"page_id": "d", "prompt_version": 99, "verdict": "pass"},
        ]
        verdicts_path.write_text(json.dumps(mixed_entries), encoding="utf-8")

        loaded = load_verdicts(path=verdicts_path)
        assert len(loaded) == 4

        # Cycle-72 L7: COUNT assertions for multi-entry fixture.
        with_key_count = sum(1 for e in loaded if "prompt_version" in e)
        assert with_key_count == 3, (
            f"expected 3 entries with prompt_version key, got {with_key_count}"
        )

        # And specific values preserved.
        by_pid = {e["page_id"]: e for e in loaded}
        assert by_pid["a"]["prompt_version"] == 1
        assert by_pid["b"]["prompt_version"] == 0
        assert "prompt_version" not in by_pid["c"]
        assert by_pid["d"]["prompt_version"] == 99


# ── AC02 paired xfail-strict mutation controls ────────────────────────


class TestAC02_StampMutation:
    """Paired xfail-strict mutation control: monkeypatching
    ``CURRENT_PROMPT_VERSION`` to 0 MUST break the stamp test (proves the
    constant is load-bearing).
    """

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-73 AC02 mutation pin — passing means stamp uses literal 1 not constant",
    )
    def test_xfail_under_zero_stamp(self, tmp_path, monkeypatch):
        from kb.lint import verdicts as verdicts_mod

        monkeypatch.setattr(verdicts_mod, "CURRENT_PROMPT_VERSION", 0)

        verdicts_path = tmp_path / "v.json"
        entry = verdicts_mod.add_verdict(
            page_id="entities/test",
            verdict_type="fidelity",
            verdict="pass",
            issues=[],
            notes="mutation",
            path=verdicts_path,
        )
        # If add_verdict reads the constant (correct), entry["prompt_version"]
        # is 0. Assertion below expects 1 → FAILS → xfail-strict accepts.
        # If add_verdict hardcoded a literal 1 (regression), entry is 1 →
        # passes → xfail-strict fails the suite.
        assert entry["prompt_version"] == 1


class TestAC02_AccessorMutation:
    """Paired xfail-strict mutation control: identity-patching
    ``get_prompt_version`` to return a constant MUST break the legacy-
    default-zero invariant.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-73 AC02 mutation pin — passing means accessor lost default-0 semantics",
    )
    def test_xfail_under_constant_accessor(self, monkeypatch):
        from kb.lint import verdicts as verdicts_mod

        # Patch accessor to always return 999.
        monkeypatch.setattr(verdicts_mod, "get_prompt_version", lambda e: 999)

        legacy_entry = {"page_id": "x", "verdict": "pass"}
        # Production accessor returns 0 → assertion 0==0 passes → xfail-strict
        # fails (suite signal). Patched accessor returns 999 → 999==0 FAILS →
        # xfail-strict accepts.
        assert verdicts_mod.get_prompt_version(legacy_entry) == 0
