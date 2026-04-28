# Cycle 49 — Implementation plan

**Date:** 2026-04-28
**Author:** primary-session per cycle-14 L1 (≥15 ACs, operator holds context post Step-5 design gate)
**Inputs:** Step-1 requirements + Step-5 design decision gate (AMEND AC3 + 6 binding conditions)

---

## TASK 1 — AC1 fold (test_cycle12_mcp_console_script.py → test_v070.py as class)

**Files:**
- `tests/test_v070.py` — APPEND new class `TestKbMcpConsoleScript` at end of file (per C6)
- `tests/test_cycle12_mcp_console_script.py` — DELETE in same commit (per C9)

**Change:** Move 3 bare functions (`test_kb_mcp_package_exposes_main`, `test_kb_mcp_server_reexports_main_and_mcp`, `test_pyproject_has_kb_mcp_script_entry`) into `class TestKbMcpConsoleScript:` as methods. All three keep their function-local imports (per cycle-23 L1: imports go AFTER the docstring closing `"""` if any; method-level imports OK since they preserve test isolation).

**Test:** Pre-fold pytest --collect-only count baseline: T0. Post-fold: T0 unchanged (3 tests preserved; method names match).

**Revert-verify (C11):** Comment out `test_kb_mcp_server_reexports_main_and_mcp` body in receiver (replace with `pass`) → pytest -k test_kb_mcp_server_reexports_main_and_mcp must FAIL. Restore.

**Criteria:** AC1, AC5 (revert-verify subset), AC6 (file count delta -1), AC9 conditions for cycle-23 L1 docstring discipline.

**Threat:** N/A (test-only)

---

## TASK 2 — AC2 fold (test_cycle9_capture_runtime_guard.py → test_capture.py as bare function)

**Files:**
- `tests/test_capture.py` — APPEND bare function `test_extract_items_via_llm_rejects_oversize_prompt` at end of file (per C7), preserving the docstring + monkeypatch pattern from source.
- `tests/test_cycle9_capture_runtime_guard.py` — DELETE in same commit (per C9)

**Change:** Move 1 bare function with 5-line docstring + 18-line body. The `import pytest` module-level import already exists in `test_capture.py`. The `from kb import capture as capture_mod` is function-local in source — keep it function-local in the receiver. The `pytest.raises(capture_mod.CaptureError)` continues to work since `capture_mod` is bound at call time.

**Test:** Pre/post fold collection count: T0 → T0. Function name unique in receiver per Step-5 C2 grep-confirmation.

**Revert-verify (C11):** Replace function body with `pass` → pytest -k test_extract_items_via_llm_rejects_oversize_prompt must FAIL. Restore.

**Criteria:** AC2, AC5 (revert-verify subset), AC6 (-1 file).

**Threat:** N/A

---

## TASK 3 — AC3 fold AMENDED (test_cycle9_package_exports.py → test_v070.py as bare function)

**Files:**
- `tests/test_v070.py` — APPEND bare function `test_ingest_source_export_lazy_loads_pipeline` BEFORE the AC1 + AC4 classes (per C7 ordering: bare functions cluster, classes follow). Since AC3 lands in same file as AC1 + AC4 in different commits, the actual ordering in final state will depend on commit order.
- `tests/test_cycle9_package_exports.py` — DELETE in same commit (per C9)

**Change:** Move 1 bare function `test_ingest_source_export_lazy_loads_pipeline` with subprocess.run PYTHONPATH probe pattern. Preserve `from __future__ import annotations` if not already present in receiver (verify per C10). Add a one-line comment in the receiver explaining the subprocess rationale per C3: `# Subprocess child verifies lazy-import contract: kb.ingest.pipeline must NOT be in sys.modules until kb.ingest.ingest_source attribute is accessed (cycle-9 PEP-562 lazy-shim).`

**Verification before commit:**
1. `grep -n "^from __future__\|^import os\|^import subprocess\|^import sys\|^from pathlib import Path" tests/test_v070.py` — confirm receiver has needed imports OR add them in same commit per C10.
2. After Edit, `pytest tests/test_v070.py::test_ingest_source_export_lazy_loads_pipeline -x` passes.

**Revert-verify (C11):** Remove the `subprocess.run` call (replace with `result = type("R",(),{"returncode":0,"stderr":""})()`) → pytest must FAIL because the assertion still requires the actual subprocess execution. Restore.

**Criteria:** AC3 (amended), AC5, AC6 (-1 file).

**Threat:** N/A

---

## TASK 4 — AC4 fold (test_cycle9_mcp_app.py → test_v070.py as class with @staticmethod helper)

**Files:**
- `tests/test_v070.py` — APPEND class `TestMcpAppInstructions` AFTER TASK 1's class (per C6 class-cluster end-of-file). Class contains `@staticmethod _instruction_tool_groups(instructions: str) -> dict[str, list[str]]:` + method `test_instructions_tool_names_sorted_within_groups`.
- `tests/test_cycle9_mcp_app.py` — DELETE in same commit (per C9)

**Change:** Move helper + test. Convert `_instruction_tool_groups` from module-level to `@staticmethod` (per C8). The single test method calls `self._instruction_tool_groups(...)` (or `cls._instruction_tool_groups(...)` if `@classmethod`; cycle-47 L1 says `@staticmethod` is canonical for module-internal helpers without `cls` dependency). Add `import asyncio` + `import re` to test_v070.py module-level if not present (per C10 — verify first).

**Verification before commit:**
1. `grep -n "^import asyncio\|^import re" tests/test_v070.py` — both must be present OR added in same commit.
2. After Edit, `pytest tests/test_v070.py::TestMcpAppInstructions::test_instructions_tool_names_sorted_within_groups -x` passes.

**Revert-verify (C11):** Replace test body with `pass` → pytest -k test_instructions_tool_names_sorted_within_groups must FAIL. Restore.

**Criteria:** AC4, AC5, AC6 (-1 file).

**Threat:** N/A

---

## TASK 5 — BACKLOG.md updates (AC7-AC16)

**Files:**
- `BACKLOG.md` — single commit grouping ALL BACKLOG edits per `feedback_batch_by_file`

**Changes (in order):**
1. **AC7** Line 126: `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28` (diskcache CVE-2025-69872)
2. **AC8** Line 129: same pattern (ragas CVE-2026-6587)
3. **AC9** Line 132: same pattern (litellm trio + wheel METADATA verification timestamp)
4. **AC10** Line 135: same pattern (pip CVE-2026-3219)
5. **AC11** Line 170: append `+ cycle-49 re-confirmed drift persists 2026-04-28; Dependabot alert ID #14 still open per .data/cycle-49/alerts-baseline.json` AND replace cycle-tag `(cycle-47+)` → `(cycle-49+)` (AC15)
6. **AC12** Line 172: same pattern as AC11 (alert ID #15)
7. **AC13** Line 158: `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28` (resolver conflicts)
8. **AC14** Lines 164/166/168: replace `(cycle-49+)` → `(cycle-50+)` AND replace `Cycle-48 re-confirmed N/A` narrative → `Cycle-49 re-confirmed N/A — prerequisite missing: <prereq>; tag bumped to cycle-50+`
9. **AC16** Line 91: append cycle-49 fold summary to Phase 4.5 HIGH #4 progress note: *"Cycle 49 continued cadence with 4 small folds: test_cycle12_mcp_console_script.py (24 LOC, 3 tests) → tests/test_v070.py, test_cycle9_capture_runtime_guard.py (33 LOC, 1 test) → tests/test_capture.py, test_cycle9_package_exports.py (36 LOC, 1 test) → tests/test_v070.py, test_cycle9_mcp_app.py (37 LOC, 1 test) → tests/test_v070.py; file count 241 → 237 (-4); test count preserved at 3025."*

**Verification before commit:**
- For each line edit, verify the OLD string exactly per C5 (`grep -n` + `Read` the line)
- After all Edits, `grep -c "cycle-49 re-confirmed" BACKLOG.md` returns 7+ (5 dep-CVE + 2 Dependabot drift)
- After all Edits, `grep -c "cycle-50+" BACKLOG.md` returns 3
- After all Edits, `grep -c "(cycle-47+)" BACKLOG.md` returns 0 (the 2 sites moved to cycle-49+)

**Criteria:** AC7-AC16

**Threat:** N/A (text-only)

---

## TASK 6 — Doc sync (AC17 + AC18)

**Files (all multi-site test/file count narrative):**
- `CLAUDE.md` — Quick Reference test count `3025 tests / 241 files` → `3025 tests / 237 files`
- `README.md` — tests/ tree-block + Phase X stats prose (per C39-L3)
- `docs/reference/testing.md` — narrative
- `docs/reference/implementation-status.md` — narrative
- `CHANGELOG.md` — APPEND new `[Unreleased]` Quick Reference entry for cycle 49 (newest first)
- `CHANGELOG-history.md` — APPEND new full per-cycle archive entry (newest first)

**Changes:**
1. **AC17** Multi-site grep BEFORE editing:
   - `grep -rn "241 files\|3025 tests / 241\|241 root-level test files" CLAUDE.md README.md docs/reference/`
   - Replace each with `237 files` / `3025 tests / 237` / `237 root-level test files` accordingly.
   - After all edits, `grep -rn "241 files\|/ 241" CLAUDE.md README.md docs/reference/` returns ZERO hits (per C26-L2 + C39-L3).
2. **AC18** CHANGELOG.md `[Unreleased]` Quick Reference entry:
   - Compact format per CHANGELOG.md format-guide
   - Items: `18 ACs / 0 src files / 4 test files deleted (folds) / 2 test files modified (receivers) + BACKLOG.md / 5 doc-narrative files`
   - Tests: `3025 → 3025` (folds preserve count)
   - Scope: one-paragraph summary
   - Detail: link to CHANGELOG-history.md anchor
3. **AC18** CHANGELOG-history.md APPEND full bullet-level entry with date anchor `2026-04-28--cycle-49`

**Verification before commit:**
- `grep -rn "241 files\|3025 tests / 241" CLAUDE.md README.md docs/reference/` returns ZERO hits
- `find tests -maxdepth 1 -name '*.py' | wc -l` returns `237`
- `pytest --collect-only 2>&1 | tail -1` returns `3025 tests collected`
- CHANGELOG.md and CHANGELOG-history.md both have a cycle 49 entry as the newest entry

**Criteria:** AC17, AC18, AC6 (test/file count verification)

**Threat:** N/A

---

## Dependencies / ordering

- TASKs 1-4 are independent of each other and of TASKs 5-6. Suggested order: 1, 2, 3, 4, 5, 6 (matches AC numbering; minimises diff conflicts within `test_v070.py` since each fold appends rather than interleaves).
- TASK 5 depends on no other; can run anywhere.
- TASK 6 MUST run last because it embeds the post-fold file count (237) and the post-implementation cycle-49 BACKLOG state.

## Skip steps

- **Step 9.5 (simplify):** SKIP — `src/` diff is zero (test-fold + doc-only).
- **Step 11 threat-model verification:** SKIP — Step 2 was skipped (pure hygiene).
- **Step 11.5 existing-CVE patch:** SKIP — all 4 baseline pip-audit advisories have either empty `fix_versions` (diskcache, ragas, pip) OR a fix blocked by transitive `click==8.1.8` constraint (litellm trio). Per cycle-22 L4 conservative posture.

## Expected commit count

6 task commits + 1 doc-sync (TASK 6 IS the doc-sync; no separate commit) = 6 total pre-PR. PR fix commits if any add to count via C30-L1 self-referential `+TBD`. Squash merge.
