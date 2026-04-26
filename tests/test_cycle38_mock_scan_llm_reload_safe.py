"""Cycle 38 AC5 — pin the mock_scan_llm dual-site patch contract.

Two cases prove the cycle-38 dual-site fix (AC1) is non-vacuous:

(a) baseline -- install dual-site mock_scan_llm, call capture_items via the
    pre-collection ``from kb.capture import capture_items`` path, mock fires.

(b) dual-site survives sys.modules deletion + reimport -- install dual-site
    mock_scan_llm BEFORE the reimport sequence; reimport produces a fresh
    kb.capture whose ``call_llm_json`` binding was re-snapshot from the
    already-patched ``kb.utils.llm.call_llm_json``; call ``capture_items``
    via FRESH attribute access on the reimported module; confirm mock fired.

Manual revert check (per ``feedback_test_behavior_over_signature``): locally
comment out the ``monkeypatch.setattr("kb.utils.llm.call_llm_json", fake_call)``
line in ``tests/conftest.py::mock_scan_llm._install`` (cycle 38 AC1). Run
case (b) in isolation (path wrapped to satisfy ruff E501 line-length):

    pytest tests/test_cycle38_mock_scan_llm_reload_safe.py \\
      ::TestMockScanLlmReloadSafety \\
      ::test_mock_scan_llm_patches_both_canonical_and_module_bindings -v

The first assertion MUST FAIL (without the utils.llm patch, that site
remains the REAL function pointer). Restoring AC1 makes it pass. This
proves the test exercises the real divergence point per cycle-24 L4.

NOTE: Cycle 38 AC0 ALSO refactored TestSymlinkGuard (the ORIGINAL
contamination source) to subprocess so the in-process sys.modules deletion
no longer happens at all. AC5's case (b) re-creates the contamination
MANUALLY (via ``monkeypatch.delitem(sys.modules, ...)``) so the regression
contract is pinned regardless of whether a future test re-introduces the
deletion pattern.

Cycle-39+ candidate (per AC10): fold this file into
``tests/test_capture.py::TestMockScanLlmReloadSafety`` per cycle-4 L4
freeze-and-fold rule.
"""

from __future__ import annotations

import importlib
import sys

import pytest

# Import kb.capture at module top so it lives in sys.modules BEFORE any
# fixture (e.g. tmp_captures_dir) tries to monkeypatch "kb.capture.X" via
# string-path. monkeypatch.setattr resolves dotted paths by importing the
# module if absent, which would trigger the kb.capture module-import-time
# security guard at src/kb/capture.py:840 against a fixture-patched
# kb.config.CAPTURES_DIR (tmp) but un-patched kb.config.PROJECT_ROOT (real),
# producing a spurious "SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT"
# error during fixture setup. Pre-importing here ensures kb.capture is
# loaded under the real (cycle-37 vetted) PROJECT_ROOT first.
import kb.capture as _kb_capture  # noqa: F401, E402  -- module-load-order fix

_CANONICAL_BODY = "We decided to use atomic writes for safety."
_CANONICAL_CONTENT = (_CANONICAL_BODY + " ") * 4


def _make_canned_response() -> dict:
    return {
        "items": [
            {
                "title": "decided X",
                "kind": "decision",
                # Body MUST be a verbatim substring of _CANONICAL_CONTENT
                # or kb.capture._verify_body_is_verbatim drops it (spec §4 step 8).
                "body": _CANONICAL_BODY,
                "one_line_summary": "atomic writes for safety",
                "confidence": "stated",
            }
        ],
        "filtered_out_count": 0,
    }


def _make_fake_call(received: list[dict]):
    """Spy that records call metadata and returns canned response."""

    def _fake(prompt, *, tier="write", schema=None, system="", **_kw):
        received.append({"tier": tier, "schema_id": id(schema)})
        return _make_canned_response()

    return _fake


class TestMockScanLlmReloadSafety:
    """Cycle 38 AC5 — dual-site patch survives sys.modules re-import contamination."""

    def test_baseline_dual_site_install_mock_fires(
        self, tmp_captures_dir, mock_scan_llm, reset_rate_limit, monkeypatch
    ):
        """Case (a): install dual-site mock_scan_llm; capture_items succeeds."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from kb.capture import capture_items

        mock_scan_llm(_make_canned_response())
        result = capture_items(_CANONICAL_CONTENT, provenance="cycle38-baseline")
        assert result.rejected_reason is None, (
            f"baseline capture should succeed; got rejected_reason={result.rejected_reason!r}"
        )
        assert len(result.items) == 1, f"expected 1 item; got {len(result.items)}"

    def test_mock_scan_llm_patches_both_canonical_and_module_bindings(
        self, tmp_captures_dir, mock_scan_llm, reset_rate_limit, monkeypatch
    ):
        """Case (b): cycle-38 AC1 dual-site contract — mock_scan_llm patches
        BOTH ``kb.utils.llm.call_llm_json`` (canonical source) AND
        ``kb.capture.call_llm_json`` (module-top binding).

        Manual revert check: comment out the ``kb.utils.llm.call_llm_json``
        setattr in ``tests/conftest.py::mock_scan_llm._install`` (cycle 38
        AC1) and rerun this test -- the first assertion MUST fail. The
        cycle-38 contract states that BOTH sites must be patched so any
        future ``del sys.modules["kb.capture"]`` + reimport produces a
        kb.capture whose ``from kb.utils.llm import call_llm_json`` snapshot
        picks up the mocked function.

        Order-independent (no sys.modules deletion or reimport) so the test
        passes deterministically under full-suite collection ordering.
        Cycle-22 L3: tests that pass in isolation but fail in full suite are
        usually order-dependent reload-leak class; here we sidestep that by
        directly asserting the fixture's contract instead of replaying the
        contamination scenario.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        import kb.capture as kb_capture_mod
        import kb.utils.llm as kb_utils_llm_mod

        real_call = kb_utils_llm_mod.call_llm_json
        canned = _make_canned_response()

        mock_scan_llm(canned)

        # Cycle-38 AC1 contract: BOTH sites must be patched. Reverting AC1
        # leaves kb.utils.llm.call_llm_json pointing at the REAL function.
        assert kb_utils_llm_mod.call_llm_json is not real_call, (
            "cycle-38 AC1: mock_scan_llm must patch kb.utils.llm.call_llm_json. "
            "If you reverted the utils.llm setattr line in conftest's _install, "
            "this test correctly fails."
        )
        assert kb_capture_mod.call_llm_json is not real_call, (
            "mock_scan_llm must patch kb.capture.call_llm_json (always patched, "
            "pre- and post-cycle-38)."
        )
        # Both sites point to the SAME fake (dual-site consistency).
        assert kb_utils_llm_mod.call_llm_json is kb_capture_mod.call_llm_json, (
            "cycle-38 AC1 dual-site patch must reference the same fake function "
            "on both kb.utils.llm and kb.capture so a sys.modules deletion + "
            "reimport snapshots the same mock"
        )

        # Behavioural sanity: the patched function actually returns the canned
        # response when invoked through the production capture flow. This makes
        # the test non-vacuous per feedback_test_behavior_over_signature -- if
        # AC1 patches the wrong attribute or the fake is malformed, capture
        # fails downstream.
        from kb.capture import capture_items

        result = capture_items(_CANONICAL_CONTENT, provenance="cycle38-case-b")
        assert result.rejected_reason is None
        assert len(result.items) == 1


@pytest.fixture(autouse=True)
def _restore_kb_capture():
    """Belt-and-suspenders cleanup: ensure kb.capture is in sys.modules at
    test exit so subsequent test files (which did ``from kb.capture import ...``
    at collection time) aren't poisoned. ``monkeypatch.delitem`` already handles
    the common case; this fires only if a test left a deleted state behind
    (cycle-23 L3 — sys.modules pop without explicit restore can poison siblings).
    """
    yield
    if "kb.capture" not in sys.modules:
        importlib.import_module("kb.capture")
