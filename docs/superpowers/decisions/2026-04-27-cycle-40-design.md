# Cycle 40 — Design decision gate

**Date:** 2026-04-27
**Owner:** Opus subagent (general-purpose, model=opus)
**Verdict:** PROCEED — all 6 questions resolved with HIGH confidence; 15 binding CONDITIONS for Step 9.

## Decisions

### D1 — AC1 fold structure (Q1)
Fold 5 sanitize tests as `class TestSanitizeErrorStrAtMCPBoundary` in `test_mcp_browse_health.py`, preceded by section comment `# ── _sanitize_error_str at MCP boundary ────────────────────────`. Class docstring references cycle-10 origin and cycle-40 fold provenance. **Rationale:** matches cycle-39 precedent (class-based fold for thematic clusters); 5-test mass justifies a class for namespacing + pytest selector convenience.

### D2 — AC2 split (Q2)
Both AC2 tests appended as bare top-level functions (no class wrapping). Test 1 → `# ── Compiler tests ──` section in `test_compile.py`; test 2 → `# --- wikilink_display_escape ---` section in `test_utils_text.py`. **Rationale:** target host files use bare functions exclusively; class wrapping a singleton test method adds zero organizational value while diverging from host convention.

### D3 — Cycle-15 AC1 comment preservation (Q3)
Migrate the 6-line cycle-15 AC1 explanatory comment VERBATIM, positioned immediately above the `@pytest.mark.parametrize` decorator inside the new class. Class docstring preface notes provenance. **Rationale:** cycle-39 verbatim-context-preservation precedent; comment documents non-obvious WHY (Python 3.11+ `date.fromisoformat` basic-format + 90d decay gate interaction) that prevents future re-introduction of the removed `20260101` case.

### D4 — AC1 imports (Q4)
Add `_safe_call`, `run_all_checks`, `health` (module ref), and `_sanitize_error_str` to `test_mcp_browse_health.py` module-top import block. Do not duplicate existing `kb_lint`. No function-body imports for AC1. **Rationale:** target uses module-top imports exclusively; cycle-23 L1 ordering doesn't apply (no `__doc__` introspection in AC1 tests).

### D5 — BACKLOG progress-note format (Q5)
Marker-append on Phase 4.5 HIGH #4 entry. Preserve original "~50 of 94" snapshot; add `(cycle-40 progress: ...)` line under existing body naming each folded source + destination. Format codified in CONDITION 11 below. **Rationale:** consistency with cycle-39 dep-CVE marker pattern; preserves WHY context that body-replace would lose.

### D6 — Test count delta verification (Q6)
Per-fold verification: `pytest --collect-only -q | tail -1` runs TWICE per fold (pre + post), 6 collections total across AC1+AC2+AC3. **Rationale:** collection cost negligible (~30s total); per-fold attribution avoids end-of-cycle binary-search-revert; cycle-15 L2 anchor-preservation enforced per-step.

## CONDITIONS (Step 9 must satisfy — load-bearing per cycle-22 L5)

1. **AC1 fold structure** [test-coverage]: 5 sanitize tests appended as `class TestSanitizeErrorStrAtMCPBoundary` in `tests/test_mcp_browse_health.py`, preceded by section comment. Class docstring references cycle-10 origin and cycle-40 fold provenance.

2. **AC1 imports** [test-coverage]: Add `_safe_call` (kb.lint._safe_call), `run_all_checks` (kb.lint.runner), `health` module ref (kb.mcp), `_sanitize_error_str` (kb.mcp.app) to module-top import block. Do not duplicate existing `kb_lint`.

3. **AC2 split — test_compile.py** [test-coverage]: `test_detect_source_drift_docstring_documents_deletion_pruning_persistence` appended as bare top-level function under `# ── Compiler tests ──` section. Inside-function `from kb.compile.compiler import detect_source_drift` import preserved verbatim.

4. **AC2 split — test_utils_text.py** [test-coverage]: `test_wikilink_display_escape_preserves_pipe_via_backslash` appended as bare top-level function under `# --- wikilink_display_escape ---` section. Inside-function `from kb.utils.text import wikilink_display_escape` import preserved verbatim (matches host's existing lazy-import convention for wikilink tests at lines 116/128/139).

5. **AC3 fold structure** [test-coverage]: 4 stale-result tests appended as `class TestFlagStaleResultsEdgeCases` in `tests/test_query.py`, preceded by section comment `# ── _flag_stale_results edge cases ─────────────────────────────`. Module-top imports for `os`, `from datetime import UTC, date, datetime, time`, `from kb.query.engine import _flag_stale_results` added if not already present.

6. **AC3 cycle-15 AC1 comment preservation** [test-coverage]: 6-line cycle-15 AC1 explanatory comment migrated VERBATIM, positioned immediately above the `@pytest.mark.parametrize("updated", ["yesterday", "04/19/2026", ""])` decorator inside the new class. Class docstring preface notes "Folded from `tests/test_cycle11_stale_results.py` cycle 40."

7. **Source files deleted** [test-coverage]: After successful per-fold verification, delete the 3 source files via `git rm` (or filesystem delete + `git add -u`). Each deletion in same commit as the corresponding fold.

8. **Per-fold count verification** [test-coverage]: After EACH of 3 fold operations, run `python -m pytest --collect-only -q | tail -1` and assert count remains 3014. Six collection runs total. Any deviation = immediate revert before proceeding.

9. **Behavior-preservation full run** [test-coverage]: After all three folds, run full suite and confirm 3003 passed + 11 skipped (3014 collected on Windows local).

10. **CLAUDE.md test-FILE count update** [doc-update]: Update Quick Reference "3014 tests / 258 files" → "3014 tests / 256 files" (3 source files deleted; 0 new files created — folds append to existing). Per C26-L2 + C39-L3, also update narrative sites: `docs/reference/testing.md`, `docs/reference/implementation-status.md`, `README.md` if they cite the file count.

11. **BACKLOG.md Phase 4.5 HIGH #4 marker-append** [doc-update]: Add marker line under existing entry: `(cycle-40 progress: 4 files folded — cycle-38 mock_scan_llm via cycle 39, plus cycle10_safe_call → test_mcp_browse_health, cycle10_linker → SPLIT to test_compile + test_utils_text, cycle11_stale_results → test_query via cycle 40; tests/ now 256 files, was 258 at cycle-39 end)`.

12. **CHANGELOG.md + CHANGELOG-history.md fold entries** [doc-update]: Compact entry to `CHANGELOG.md [Unreleased]` (Items / Tests / Scope / Detail). Full per-cycle bullet detail in `CHANGELOG-history.md`.

13. **AC4-AC10 re-verification documentation** [doc-update]: Re-verify markers per Step 11.5; document with `(cycle-40 re-confirmed 2026-04-27)` if state matches; otherwise update with delta.

14. **No new trust boundaries** [test-coverage]: Zero new `_validate_page_id` / `_validate_path_under_project_root` call sites; zero new MCP tools; zero new public API surface.

15. **Cleanup scratch files** [doc-update]: Per `feedback_cleanup_scratch_files`, delete any `findings.md` / `progress.md` / `task_plan.md` / `claude4.6.md` before marking cycle done.

## Blast radius / Reversibility

- Blast radius: minimal — test-file relocation + doc-only edits + zero src/kb/ changes. Test count invariant 3014. File count 258 → 256.
- Reversibility: per-fold verification (Q6) ensures single-fold revert without disrupting siblings. Each fold = 1 source delete + 1 target append — `git checkout HEAD~1 -- <files>` reverses cleanly.
- Convention adherence: Q1/D1 → cycle-39 class precedent; Q2/D2 → host-file shape; Q3/D3 → cycle-39 verbatim preservation; Q4/D4 → host module-top imports; Q5/D5 → cycle-39 marker-append; Q6/D6 → cycle-15 L2 per-step verification.

## VERDICT
**PROCEED** — no open questions; low blast radius; reversible per-fold; convention-aligned with cycle 39.
