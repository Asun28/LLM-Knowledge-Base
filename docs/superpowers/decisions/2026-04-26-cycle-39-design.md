# Cycle 39 — Design Decision Gate

**Date:** 2026-04-26
**Owner:** Opus 4.7 primary session (per skill: run Step 5 even on trivial cycles to catch unstated assumptions)

## Analysis

Cycle 39 is a backlog hygiene + dep-drift re-verification + cycle-38 test fold cycle. Eleven ACs total, all small and mechanical. The cycle introduces zero `src/kb` production code changes. Three open questions surface from edge-case scan; each gets resolved here so Step 9 implementation is unambiguous.

The fundamental shape is: (1) capture pip-audit / Dependabot baselines (already done at Step 2), (2) re-confirm seven existing BACKLOG entries are still accurate, (3) fold one cycle-tagged test file into the canonical test_capture.py per cycle-4 L4 freeze-and-fold rule, (4) doc-sync. No new code paths, no new attack surface. The risk profile is very low — the worst-case wrong call here is a cosmetic doc inconsistency, fixable in cycle 40 without merge revert.

The three open questions below all involve the test fold mechanics. Resolving them at Step 5 prevents Step 9 from making silent design choices that R1/R2 would catch later.

## Open question Q1 — autouse fixture scope after fold

**Options:**
- (A) Move the `_restore_kb_capture` autouse fixture from the cycle-38 file into `tests/test_capture.py` at module scope (autouse fires on every test in the file).
- (B) Class-scope the autouse fixture inside `TestMockScanLlmReloadSafety` so only the 2 folded tests get the cleanup.
- (C) Drop the fixture entirely on the assumption that test_capture.py's existing tests don't pop kb.capture from sys.modules (per the file-search done at Step 4 design eval).

**ARGUE:** Option (A) preserves the fixture's broadest defensive value but expands its blast radius from 2 tests to 1100+ tests in test_capture.py. The fixture body is `yield + (if "kb.capture" not in sys.modules: importlib.import_module("kb.capture"))` — fast no-op when kb.capture is loaded (which it always is for tests that import from kb.capture, which test_capture.py does at module-top line 20). So the autouse cost is negligible and the defensive coverage extends to any future test in the file that decides to delete kb.capture from sys.modules.

Option (B) class-scopes via a method-level fixture, restricting the cleanup to exactly the 2 folded tests. Matches the cycle-38 file's apparent intent (fixture lives in the same file as the tests it protects). But class-scoping requires nesting the fixture INSIDE the class, which is unusual for autouse and slightly harder to read.

Option (C) is the riskiest — cycle-23 L3 (sys.modules.pop without monkeypatch.delitem poisons sibling tests) is exactly the failure mode this fixture defends against. Dropping the fixture on the assumption that test_capture.py's other tests "won't" pop kb.capture is a fragile assumption — a future cycle-N test added at line 1700 of test_capture.py might pop kb.capture without realizing the contract.

**DECIDE:** Option (A) — move to module-scope autouse. Negligible cost (yield + conditional import is microseconds per test, no measurable overhead on a 3-second collection time), broadest defensive coverage, matches "belt-and-suspenders" intent in the original docstring.

**RATIONALE:** The fixture's design comment in the cycle-38 file explicitly says "belt-and-suspenders cleanup" — that's a defense-in-depth pattern, not a precision tool. Option (A) preserves the defense-in-depth shape; the alternatives narrow the protection.

**CONFIDENCE:** HIGH.

## Open question Q2 — module-level helpers (`_CANONICAL_BODY` / `_make_canned_response`)

**Options:**
- (A) Keep helpers at module level in test_capture.py (matches cycle-38 file shape).
- (B) Inline as class attributes inside `TestMockScanLlmReloadSafety`.
- (C) Promote to fixture(s).

**ARGUE:** Option (A) preserves the original cycle-38 shape with zero refactor — the helpers don't collide with any existing test_capture.py names (verified via grep at Step 4). The two helpers (`_CANONICAL_BODY`/`_CANONICAL_CONTENT` constants + `_make_canned_response()`/`_make_fake_call()` functions) are private (`_` prefix) and module-scoped, so they won't pollute pytest collection.

Option (B) inlines as class-level attributes. Slightly cleaner namespace but needs `_make_canned_response` to be `@staticmethod` (it doesn't use `self`), adds clutter to the class body without behavioral benefit.

Option (C) promotes to fixtures. Overkill for static test data; fixtures are for setup/teardown, not for fixed strings.

**DECIDE:** Option (A) — keep at module level.

**RATIONALE:** Per cycle-4 L4 freeze-and-fold rule, fold preserves behavior. The helpers worked at module level in the cycle-38 file; they work the same way in test_capture.py. Refactoring would be over-engineering a hygiene cycle.

**CONFIDENCE:** HIGH.

## Open question Q3 — defensive `import kb.capture as _kb_capture` line

**Options:**
- (A) Drop the defensive pre-import line because test_capture.py already does `from kb.capture import (...)` at line 20 — kb.capture is loaded before any fixture runs.
- (B) Keep the defensive line as a no-op for documentation purposes.

**ARGUE:** The original cycle-38 file had this comment block explaining the line:

> ```
> # Import kb.capture at module top so it lives in sys.modules BEFORE any
> # fixture (e.g. tmp_captures_dir) tries to monkeypatch "kb.capture.X" via
> # string-path. monkeypatch.setattr resolves dotted paths by importing the
> # module if absent, which would trigger the kb.capture module-import-time
> # security guard at src/kb/capture.py:840 against a fixture-patched
> # kb.config.CAPTURES_DIR (tmp) but un-patched kb.config.PROJECT_ROOT (real),
> # producing a spurious "SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT"
> # error during fixture setup. Pre-importing here ensures kb.capture is
> # loaded under the real (cycle-37 vetted) PROJECT_ROOT first.
> ```

In test_capture.py, the existing line 20 `from kb.capture import (...)` ALREADY accomplishes the same thing (loads kb.capture into sys.modules at module-top, before any fixture runs) — so the defensive line is genuinely redundant.

Option (A) drops the redundant line — cleaner, matches the spirit of fold-into-canonical (eliminate duplication).

Option (B) keeps it as a documentation comment block — preserves the rationale for future readers but adds dead code.

**DECIDE:** Option (A) — drop the line, but PRESERVE the rationale by adding a one-line comment near the new TestMockScanLlmReloadSafety class pointing at the existing module-top import as the load-bearing import.

**RATIONALE:** The fold is INTO the canonical file precisely because the canonical file already has the equivalent import. Keeping the redundant line would be a smell. The rationale is a comment trail; the load-bearing mechanism is the existing `from kb.capture import ...` at line 20.

**CONFIDENCE:** HIGH.

## DECISIONS (final — Step 9 must satisfy)

| # | Decision | Source |
|---|---|---|
| D1 | Append `class TestMockScanLlmReloadSafety` at end of `tests/test_capture.py` (after `class TestAdversarialAuditFixes`); paste both test methods + their docstrings verbatim | AC8 |
| D2 | Append module-level helpers (`_CANONICAL_BODY`, `_CANONICAL_CONTENT`, `_make_canned_response`, `_make_fake_call`) immediately before `class TestMockScanLlmReloadSafety` (Q2 → A) | AC8 |
| D3 | Add `import importlib` to test_capture.py's import block (test_capture.py already has `import sys`) | AC8 |
| D4 | Append the `@pytest.fixture(autouse=True) def _restore_kb_capture():` AT END of test_capture.py (after the new class) — module-level autouse per Q1 → A | AC8 |
| D5 | DROP the defensive `import kb.capture as _kb_capture` line (Q3 → A); add a 1-line comment near the new class noting that the existing `from kb.capture import ...` at line 20 is the load-bearing import | AC8 |
| D6 | Delete `tests/test_cycle38_mock_scan_llm_reload_safe.py` after the fold | AC8 |
| D7 | Per `feedback_batch_by_file`: one commit per file group. Cycle 39 commit graph: (a) `BACKLOG.md` re-confirmation edits + entry deletion (1 commit); (b) `tests/test_capture.py` add + `tests/test_cycle38_mock_scan_llm_reload_safe.py` delete (1 commit, atomic move semantics); (c) `CHANGELOG.md` + `CHANGELOG-history.md` + `docs/superpowers/decisions/*` (1 commit). Total: ~3 implementation commits + 1 self-review commit = 4 expected | per skill |
| D8 | BACKLOG re-confirmation MARKER FORMAT: append " *(cycle-39 re-confirmed 2026-04-26)*" inside the existing parenthetical OR as a new sentence; preserve all existing prose | AC1-AC7 |
| D9 | Per cycle-22 L5 design CONDITIONS: each AC's "test" column in the requirements doc maps to a verifiable check at Step 9. Step 11 verifies T1+T2+T3+T4 (the 4 threat-model items) against the diff | per skill |
| D10 | Per C30-L1: cycle-39 commit-count claim in CHANGELOG uses "+TBD"; backfill post-merge on `main` with a separate post-merge hotfix commit | per skill |
| D11 | NO `src/kb/*.py` edits permitted in cycle 39. If Step 9 finds it needs one, treat as DESIGN-AMEND and re-run Step 5 (per cycle-17 L3 scope-narrowing routes back to Step 5) | per skill |

## CONDITIONS (Step 09 must satisfy verbatim)

1. **BEFORE the test fold commit lands**, run `pytest tests/test_capture.py -v` to confirm baseline of folding-target file passes alone.
2. **AFTER the test fold commit lands**, run the FULL suite (`python -m pytest -q`) — per cycle-22 L3 isolation passes don't prove full-suite green; full-suite is authoritative.
3. The cycle-38 file's `_restore_kb_capture` fixture body is preserved verbatim including the `if "kb.capture" not in sys.modules: importlib.import_module("kb.capture")` clause AND its docstring (per cycle-23 L3 — the fixture defends a real failure class, not just paranoia).
4. The two test methods preserve the manual-revert-check guidance in their docstrings — that guidance is part of the regression contract per `feedback_test_behavior_over_signature`.
5. Test count must remain `3014 collected / 3003 passed + 11 skipped on Windows local`. Folding doesn't add or remove tests, it relocates them.

## VERDICT

**PROCEED.** No ESCALATE conditions met (low blast radius, reversible, primary-session has full context). Zero open questions remain after the three Q1/Q2/Q3 resolutions above.
