# Cycle 49 — Design decision gate

**Date:** 2026-04-28
**Owner:** primary-session per cycle-21 L1 + cycle-48 precedent (conditions are doc/design gaps, not code-exploration; operator holds full context post requirements + R1 verification)
**Inputs:** Step-1 requirements + Step-2 baseline + R1 DeepSeek V4 Pro verdict (APPROVE-WITH-CONDITIONS, 5 conditions)
**Verdict:** **APPROVE WITH 1 AMENDMENT + 6 CONDITIONS**

---

## R1 DeepSeek conditions resolved

R1 emitted 5 conditions. Each is now binding on Step 9 implementation:

| # | R1 condition | Resolution |
|---|---|---|
| C1 | Pre-fold verification of source file LOC + exact tests | Already grep-confirmed at Step 4 receiver-verification pass: 24 LOC / 3 tests, 33 LOC / 1 test, 36 LOC / 1 test, 37 LOC / 1 test. Step 9 must re-verify per task before deletion. |
| C2 | Verify `test_capture.py` has no `test_extract_items_via_llm_rejects_oversize_prompt` | Grep-confirmed zero collisions in BOTH `test_v070.py` AND `test_capture.py` for ALL 6 fold-target test names + 3 proposed class names. R1 condition CLOSED. |
| C3 | Justify subprocess use in `test_v070.py` (AC3) | Subprocess is the correct test mechanism for the lazy-import contract — see cycle-9 design rationale: a child interpreter MUST start fresh to confirm `kb.ingest.pipeline` is NOT in `sys.modules` until the lazy attribute is accessed. The test's PYTHONPATH wiring (line 14-19 of source) cycle-7 cleared per `feedback_subprocess_pythonpath`. Add a one-line comment in the receiver explaining the subprocess rationale (per cycle-23 L1 docstring discipline). NO BACKLOG entry — subprocess is canonical, not fragile. |
| C4 | Final file/test counts confirmed via `find`/`pytest --collect-only` | Step 10 CI hard gate runs both. Step 12 doc update re-verifies per cycle-15 L4 (after any R1/R2 PR-fix commits). |
| C5 | Verify cycle tag strings before replacement | Step 9 grep-verifies exact strings `cycle-49+` (AC14) and `cycle-47+` (AC15) at the cited BACKLOG line numbers BEFORE any `Edit` call. Per cycle-24 L1 single-line literal Edit + post-edit grep verification. |

## Binding amendment — AC3 host-shape (R1 missed)

**A1. AC3 receiver-shape alignment (C40-L5).** R1 did not flag this; primary catches it on receiver inspection.

`tests/test_v070.py` is purely bare-function shaped — 28 bare functions, 0 classes. Per C40-L5 the design must include a "Source file inspection results" section establishing host-shape.

The original design proposed:
- AC1 → new class `TestKbMcpConsoleScript` (3 tests)
- AC3 → new class `TestPackageExportLazyLoading` (1 test)
- AC4 → new class `TestMcpAppInstructions` (1 test + helper)

Host-shape evaluation per cycle-43 L4 ("new class introduced for fold cohesion when receiver mixes both"):
- AC1: 3 tests with strong cohesion (all `kb-mcp` console-script semantics) → class JUSTIFIED for grouping
- AC3: 1 test, no helper, no cohesion partner → **AMEND to bare function** matching host-shape
- AC4: 1 test + private helper `_instruction_tool_groups` needing homing → class with `@staticmethod` JUSTIFIED for helper

**Amended AC3 (binding):** Fold `tests/test_cycle9_package_exports.py` test as a top-level bare function `test_ingest_source_export_lazy_loads_pipeline` directly into `tests/test_v070.py`. NO wrapping class. This matches the receiver's pure bare-function host-shape and avoids over-engineering a single-test class.

AC1 and AC4 retain their original class shape (cohesion + helper-homing justifications).

## Additional Step-9 conditions (binding)

In addition to R1's C1-C5 + the AC3 amendment:

**C6. Class insertion order (AC1, AC4).** When inserting `TestKbMcpConsoleScript` and `TestMcpAppInstructions` classes into `test_v070.py`, append at the END of the file (after the last bare function `test_mcp_all_tools_registered`). Do NOT interleave classes between bare functions — preserves git-blame readability and mirrors the cycle-47 pattern where new test classes were appended to receivers.

**C7. Bare-function insertion (AC2, AC3 amended).** Append both at the END of their receivers (`test_capture.py` and `test_v070.py`). For `test_v070.py` specifically, insert AC3 BEFORE the AC1+AC4 classes if both groups are added in the same file; that is, the file end will be: `<existing bare functions> ... <AC3 bare function> ... <AC1 class> <AC4 class>`. Bare functions cluster, classes follow.

**C8. Helper migration (AC4).** The private `_instruction_tool_groups` helper in `test_cycle9_mcp_app.py` becomes `@staticmethod _instruction_tool_groups` inside `TestMcpAppInstructions`. The single test method calls `self._instruction_tool_groups(...)`. Re-test the call site post-fold; per cycle-47 L1 staticmethod is the right call (no `self` dependency in helper body).

**C9. Source-file deletion in same commit as fold (AC1-AC4).** Each fold + corresponding source deletion happens in ONE commit, NOT split across commits. This matches cycles 47/48 pattern and avoids a stale-source intermediate state where pytest collects tests from BOTH files (would temporarily increase test count).

**C10. Module-level imports preserved into receiver as appropriate.** The fold candidates have these module-level imports:
- `test_cycle12_mcp_console_script.py` — none (uses local imports per test)
- `test_cycle9_capture_runtime_guard.py` — `import pytest` (already in `test_capture.py`)
- `test_cycle9_package_exports.py` — `from __future__ import annotations`; `import os`, `subprocess`, `sys`; `from pathlib import Path` (most likely already in `test_v070.py`; verify per task)
- `test_cycle9_mcp_app.py` — `import asyncio`, `import re` (verify per task)

Step 9 verifies these are in the receiver OR adds them in the same commit.

**C11. Revert-verify minimum (AC5 spec).** AC5 says "single representative test per fold". For multi-test folds (AC1's 3 tests), the representative is the test most likely to fail under deletion of the moved code. Pick:
- AC1: `test_kb_mcp_server_reexports_main_and_mcp` (exercises the `kb.mcp_server` shim at runtime — fails if the moved test method is replaced with `pass`)
- AC2: `test_extract_items_via_llm_rejects_oversize_prompt` (single test; revert-verify by replacing the method body with `pass` and confirming pytest reports failure)
- AC3: `test_ingest_source_export_lazy_loads_pipeline` (single test; revert-verify by removing the `subprocess.run` call)
- AC4: `test_instructions_tool_names_sorted_within_groups` (single test; revert-verify by replacing assertion with `pass`)

Each revert-verify recorded in the per-task commit message footer: `Revert-verified: <test-name> body comment-out → pytest -x reports FAIL on …`.

## Scope-out items (deliberately deferred)

- **`test_cycle9_lint_checks.py` (42 LOC) NOT in cycle 49.** Adjacent to cycle-44 M1 lint-checks split surface; defer to cycle-50+ when split has fully settled (cycle-46 LOW closeout was 2 cycles ago, lint module still in active surface).
- **No other small versioned files in cycle 49.** Inspection found `test_cycle12_conftest.py` (49 LOC) and `test_cycle17_capture_prompt.py` (52 LOC) as next candidates; defer per "small fold cadence" rule (4 folds is meaningful step-up from cycle 48's 2 folds).
- **No same-class-peer fold extension.** R1 did not flag any required peer expansion; cycle-49 scope is bounded as 4 folds.

## Final decided design

| AC | Decision | Rationale |
|---|---|---|
| AC1 | KEEP — fold as class `TestKbMcpConsoleScript` in test_v070.py | 3-test cohesion warrants class wrapper per cycle-43 L4 |
| AC2 | KEEP — fold as bare function in test_capture.py | Host-shape mixed; bare-function cluster region matches |
| AC3 | **AMEND** — fold as bare function (NOT class) in test_v070.py | Host-shape pure bare-function; single test does not warrant class |
| AC4 | KEEP — fold as class `TestMcpAppInstructions` with `@staticmethod` helper | Helper needs homing; class is right container per C40-L5 |
| AC5 | KEEP | Revert-verify per C40-L3 across all 4 folds |
| AC6 | KEEP — file 241→237 (-4); test 3025 preserved | |
| AC7-AC13 | KEEP — mechanical timestamp refresh on 7 BACKLOG entries | |
| AC14 | KEEP — bump cycle-49+ → cycle-50+ on 3 N/A entries | |
| AC15 | KEEP — bump cycle-47+ → cycle-49+ on 2 Dependabot drift entries | |
| AC16 | KEEP — append cycle-49 progress to Phase 4.5 HIGH #4 note | |
| AC17 | KEEP — multi-site test/file count update per C26-L2 + C39-L3 | |
| AC18 | KEEP — CHANGELOG + CHANGELOG-history entries | |

**Confidence:** HIGH on all decisions. AC3 amendment is host-shape alignment, not new scope.

**Open questions:** none.
