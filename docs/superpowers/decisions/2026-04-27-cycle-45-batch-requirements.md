# Cycle 45 Batch Requirements

**Date:** 2026-04-27
**Branch:** cycle-45-batch
**Worktree:** D:/Projects/llm-wiki-flywheel-c45
**Scope:** Phase 4.6 close (4 MEDIUM + 1 LOW) + cycle-43 carry-overs (AC10 fold + 3 vacuous-test upgrades)

> **Provenance.** This doc is adopted from cycle-44's abandoned requirements artifact (cycle-44 worktree at `D:/Projects/llm-wiki-flywheel-c44`, untracked). Cycle 44 stalled mid-Step 5 (design eval prompt prepared, never dispatched). The scope is unchanged because Phase 4.6 MEDIUM/LOW + cycle-43 deferrals are still open on `main` (verified against `BACKLOG.md` 2026-04-27). LOC counts re-verified against current main (lint/augment.py drifted 1186→1189; otherwise unchanged). The Step-1 doc-write happened via primary-session adoption rather than fresh Codex dispatch — to be documented in Step-16 self-review per dev_ds primary-session-shortcut precedent (cycle-14 L1 / C37-L5).

---

## 1. Problem

### M1 — `lint/checks.py` monolith (1046 LOC)

Per BACKLOG.md Phase 4.6 MEDIUM: `lint/checks.py` (1046 LOC) houses frontmatter, dead-link, orphan, cycle-detection, staleness, and duplicate-slug rules in a single file. Cycle-30 added consistency lint, cycle-31 added deep-lint — every new rule grows the same module, defeating per-rule test isolation. **Suggested fix:** split into `lint/checks/<rule>.py` per rule + `lint/checks/__init__.py` registry.

### M2 — `lint/augment.py` monolith (1189 LOC) + L1 siblings

Per BACKLOG.md Phase 4.6 MEDIUM: `lint/augment.py` (1189 LOC; was 1186 at cycle-44 baseline) contains collector, proposer, URL fetcher, persister, outcome recorder, and post-ingest quality logic. The dual `_augment_manifest.py` (213 LOC) and `_augment_rate.py` (110 LOC) sibling helpers further confirm decomposition is overdue. **Suggested fix:** convert to `lint/augment/` package with `collector.py` / `proposer.py` / `fetcher.py` / `persister.py` / `quality.py`; absorb `_augment_manifest.py` and `_augment_rate.py` as `manifest.py` / `rate.py` inside the package. This simultaneously closes Phase 4.6 LOW: `lint/_augment_manifest.py` and `lint/_augment_rate.py` — leading-underscore private siblings used only by `lint/augment.py`.

### M3 — `mcp/core.py` monolith (1149 LOC)

Per BACKLOG.md Phase 4.6 MEDIUM: `mcp/core.py` (1149 LOC) contains query, ingest, capture, compile, and helper-tool implementations co-resident despite the cycle-4-13 split that already moved browse / health / quality out. Adding any Phase 5 write-path tool (`kb_review_page` etc., open in Phase 4.5 MEDIUM) would land here by default. **Suggested fix:** continue the cycle-4-13 pattern — add `mcp/ingest.py` and `mcp/compile.py`; keep `core.py` for the FastMCP app + cross-cutting helpers ≤ 300 LOC.

### M4 — Dual atomic-write helpers

Per BACKLOG.md Phase 4.6 MEDIUM: `capture.py:461` (`_exclusive_atomic_write`) and `utils/io.py:144` (`atomic_text_write`) are two write-helpers with different invariants — capture uses `O_EXCL` for slug-collision detection; utils uses tempfile+rename for crash-atomicity. Cycle-38 AC6 widened test-side patching to cover both sites but the duplication itself was not collapsed; any future write-discipline change (e.g., fsync parent dir, lock acquisition) must be applied twice. **Suggested fix:** single `atomic_text_write(path, content, *, exclusive=False)` in `utils/io.py` accepting both modes; capture imports it; cycle-38 dual-site test patches collapse to a single patch. Per cycle-15 L1, the unified function MUST preserve the full contract of both predecessors: crash-atomicity (tempfile+rename) for `exclusive=False` AND `O_EXCL` slug-collision detection for `exclusive=True`.

### Cycle-43 carry-overs — AC10 fold + 3 vacuous-test upgrades

The BACKLOG.md cycle-43 deferral note: `tests/test_cycle12_sanitize_context.py` → `tests/test_mcp_core.py` postponed due to active cycle-42 Phase 4.6 dedup interference. The `_sanitize_conversation_context` symbol survives cycle-42; commit `eee0e5c` is the post-cycle-43 head and the merge surface is now clear.

The three vacuous-test upgrade candidates flagged C40-L3 + C41-L1 in BACKLOG.md:

1. `tests/test_models.py::test_graph_builder_documents_case_sensitivity_caveat` — docstring-content assertion; upgrade path is **DELETE** (behavior already covered by `test_page_id_*` in `test_utils.py`).
2. `tests/test_utils_io.py::test_load_page_frontmatter_docstring_documents_mtime_caveat` — docstring-content assertion; upgrade path is **REPLACE** with a behavioral mtime-collision test.
3. `tests/test_utils_io.py::test_cycle12_io_doc_caveats_are_present` — docstring-content assertion; upgrade path is **DELETE** the `atomic_*_write` portion (redundant vs `test_sweep_orphan_tmp_*`) and **REPLACE** the `file_lock` PID-recycling portion with a behavioral stale-lock-reaping test.

---

## 2. Non-Goals

- **NO functional or behavior changes.** Every item in this cycle is a pure structural refactor (file splits, package conversions, helper consolidation) or a test-quality upgrade. Observable behavior of all public APIs, CLI subcommands, and MCP tool outputs is preserved unchanged.
- **NO Phase 5 items touched.** Phase 5 features (community proposals, inline claim tags, URL-aware ingest, semantic chunking, autonomous research loop, etc.) are explicitly out of scope.
- **NO new lint rules.** The checks.py split creates per-rule files for existing rules only; no new checking logic is added.
- **NO changes to public CLI or MCP tool surface.** All 28 MCP tool names (cycle-20 L2 corrected count) and all 24 CLI subcommands are preserved as-is.
- **NO renames of tested public functions.** `check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `fix_dead_links`, `run_augment`, `save_page_frontmatter`, `_build_proposer_prompt`, `_format_proposals_md`, `atomic_text_write`, `kb_compile`, `kb_query`, `kb_ingest`, `_sanitize_conversation_context`, and all other named public symbols remain importable from their current paths.

### Constraints from prior cycle lessons

- **cycle-23 L5:** Package `__init__.py` files MUST preserve `from <package> import <symbol>` semantics for any caller. Re-export shims required in every new `__init__.py`.
- **C42-L5:** All re-export lines in `__init__.py` files MUST carry an explicit `# noqa: F401` comment plus a one-sentence explanation comment to prevent `ruff --fix` from stripping them.
- **C42-L3:** Function moves invalidate `monkeypatch.setattr` even when the function is re-exported. Patch sites must be migrated to target the NEW canonical module. The implementation plan must grep all current `monkeypatch`/`patch(` sites BEFORE moving any module-global symbol — three greps (string-form, reference-form via module variable, broader) per cycle-19 L1.
- **cycle-15 L1:** Any AC that says "replace existing X with Y" MUST explicitly note that Y preserves X's full contract (both crash-atomicity AND `O_EXCL` semantics for M4).
- **cycle-19 L2:** Module-top file reads MUST become lazy `_get_X()` accessors when the module participates in a reload cascade. Applies to the new `lint/augment/manifest.py` and `lint/augment/rate.py`.

---

## 3. Acceptance Criteria

### M1 — checks.py split (AC1-AC10)

**AC1.** `src/kb/lint/checks/` package directory exists containing an `__init__.py` registry file. The original `src/kb/lint/checks.py` flat file is removed. Importing `kb.lint.checks` succeeds without error.

**AC2.** Each lint rule group has its own sub-module file. At minimum the following files exist: `src/kb/lint/checks/frontmatter.py`, `src/kb/lint/checks/dead_links.py`, `src/kb/lint/checks/orphan.py`, `src/kb/lint/checks/cycles.py`, `src/kb/lint/checks/staleness.py`, `src/kb/lint/checks/duplicate_slug.py`, `src/kb/lint/checks/consistency.py`, `src/kb/lint/checks/inline_callouts.py`. Each file exists on disk and contains at least one function definition.

**AC3.** `src/kb/lint/checks/__init__.py` re-exports every function importable from the original `kb.lint.checks` flat module. Target symbols include at minimum: `check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `fix_dead_links`, plus any other top-level callable. Each re-export line carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`. `from kb.lint.checks import check_source_coverage` resolves to the function object in the submodule.

**AC4.** `tests/test_lint.py` passes without modification. `python -m pytest tests/test_lint.py -x` exits 0.

**AC5.** `tests/test_backlog_by_file_cycle1.py`, `tests/test_backlog_by_file_cycle3.py`, `tests/test_backlog_by_file_cycle7.py` pass without modification (they import `from kb.lint.checks import check_source_coverage` and `from kb.lint import checks`).

**AC6.** `tests/test_cycle15_lint_authored_drift.py`, `tests/test_cycle15_lint_decay_wiring.py`, `tests/test_cycle15_lint_status_mature.py` pass without modification.

**AC7.** `tests/test_cycle16_duplicate_slugs.py` and `tests/test_cycle16_inline_callouts.py` pass without modification.

**AC8.** `tests/test_cli.py` passes without modification. This file patches `kb.lint.checks.WIKI_DIR` and `kb.lint.checks.RAW_DIR`; those module-level attributes MUST remain accessible at `kb.lint.checks.WIKI_DIR` / `RAW_DIR` after the package split. Plan-gate must verify `WIKI_DIR`/`RAW_DIR` constants are re-exported at the package level (not just at the submodule level).

**AC9.** `tests/test_fixes_v060.py` and `tests/test_lint_fix_v093.py` pass without modification.

**AC10.** `tests/test_lint_runner.py` passes without modification. `lint.runner.run_all_checks` enumeration semantics MUST be preserved.

### M2 — augment.py package conversion (AC11-AC18)

**AC11.** `src/kb/lint/augment/` package directory exists containing `__init__.py`, `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py`. The original `src/kb/lint/augment.py`, `src/kb/lint/_augment_manifest.py`, and `src/kb/lint/_augment_rate.py` are removed. All 8 new files exist; all 3 removed files are absent.

**AC12.** `src/kb/lint/augment/__init__.py` re-exports every symbol importable from the original flat `kb.lint.augment` module. Target symbols include at minimum: `run_augment`, `save_page_frontmatter`, `_build_proposer_prompt`, `_format_proposals_md`. Each re-export line carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`. `from kb.lint.augment import run_augment` and `from kb.lint.augment import _build_proposer_prompt` each resolve to the correct function.

**AC13.** `manifest.py` and `rate.py` inside the package do NOT perform module-top disk reads (per cycle-19 L2). Any JSON state previously loaded at import time MUST be wrapped in a lazy `_get_X()` accessor called on first use. Importing `kb.lint.augment` with no wiki directory configured does not raise `FileNotFoundError` or perform disk I/O.

**AC14.** Monkeypatch patch sites in `tests/test_cycle13_frontmatter_migration.py` (sites that target `kb.lint.augment.call_llm_json` via either `patch("kb.lint.augment.call_llm_json", ...)` or `monkeypatch.setattr(augment, "call_llm_json", ...)` reference form) are updated to target the NEW canonical submodule of `call_llm_json` (per C42-L3). All `test_cycle13_frontmatter_migration.py` tests pass.

**AC15.** Monkeypatch patch sites in `tests/test_cycle17_resume.py` (sites targeting `kb.lint.augment.run_augment`) are updated to the canonical module location. All `test_cycle17_resume.py` tests pass.

**AC16.** `tests/test_backlog_by_file_cycle1.py`, `tests/test_cycle9_lint_augment.py`, `tests/test_cycle5_hardening.py` pass without modification.

**AC17.** `tests/test_cycle14_augment_key_order.py` passes without modification.

**AC18.** Full lint test suite passes: `python -m pytest tests/test_lint.py tests/test_cycle13_frontmatter_migration.py tests/test_cycle14_augment_key_order.py tests/test_cycle15_lint_authored_drift.py tests/test_cycle15_lint_decay_wiring.py tests/test_cycle15_lint_status_mature.py -x` exits 0.

### M3 — mcp/core.py split (AC19-AC24)

**AC19.** `src/kb/mcp/ingest.py` and `src/kb/mcp/compile.py` are created. Ingest-related tool implementations (`kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_capture`, `kb_compile_scan`) move to `ingest.py`. Compile-related implementations (`kb_compile` and compile-specific helpers) move to `compile.py`. `core.py` retains the FastMCP app instance (or re-export thereof), cross-cutting helpers, and `_sanitize_conversation_context`. Target: `core.py` line count ≤ 300 LOC after the split. If the cap is infeasible due to legitimate cross-cutting helpers, the plan-gate may amend to ≤ 350 LOC with explicit justification per cycle-44 brainstorm Q6.

**AC20.** Re-exports in `core.py` (or via `kb.mcp.core` package shim if structure changes) preserve `from kb.mcp.core import kb_ingest`, `from kb.mcp.core import kb_compile`, `from kb.mcp.core import _sanitize_conversation_context` for all existing callers. Both `from kb.mcp.core import kb_compile` and `from kb.mcp.core import kb_ingest` succeed without `ImportError`.

**AC21.** The cycle-43 AC10 carry-over fold is complete: `tests/test_cycle12_sanitize_context.py` is deleted and its tests are merged into `tests/test_mcp_core.py`. The folded tests cover at minimum: empty list input, list-over-limit truncation, and context content passthrough for `_sanitize_conversation_context`. Per cycle-17 L3, if dedup detects cycle-12 tests already covered in `test_mcp_core.py`, redundant duplicates are dropped with an inline `DESIGN-AMEND` note in the cycle-45 design doc. `tests/test_cycle12_sanitize_context.py` does not exist post-fold; `python -m pytest tests/test_mcp_core.py -x -k sanitize` passes with ≥ 5 tests collected.

**AC22.** `tests/test_compiler_mcp_v093.py` passes without modification (`from kb.mcp.core import kb_compile` + inline `from kb.mcp.core import kb_query`).

**AC23.** `tests/test_cycle11_task6_mcp_ingest_type.py` and `tests/test_cycle17_mcp_tool_coverage.py` pass without modification.

**AC24.** `tests/test_cycle16_kb_query_save_as.py` passes without modification (`from kb.mcp import core as mcp_core`).

### M4 — atomic_text_write consolidation (AC25-AC27)

**AC25.** `src/kb/utils/io.py::atomic_text_write` gains an `exclusive: bool = False` keyword-only parameter. When `exclusive=True`, uses `os.open(..., os.O_CREAT | os.O_EXCL | os.O_WRONLY)` for slug-collision detection (raises `FileExistsError` on conflict). When `exclusive=False` (default), uses the existing tempfile+rename crash-atomicity path. Function signature: `def atomic_text_write(path: Path | str, content: str, *, exclusive: bool = False) -> None`. Per cycle-15 L1, both contracts are preserved. Calling `atomic_text_write(existing_path, "x", exclusive=True)` raises `FileExistsError`; calling with `exclusive=False` to a new path succeeds; existing crash-atomicity test cases continue to pass unchanged.

**AC26.** `src/kb/capture.py` removes its internal `_exclusive_atomic_write` helper and instead calls `atomic_text_write(..., exclusive=True)` imported from `kb.utils.io`. `grep "_exclusive_atomic_write" src/kb/capture.py` returns no matches; `python -c "from kb.capture import CaptureResult"` succeeds (the public surface is unchanged).

**AC27.** The dual-site monkeypatch in `tests/test_capture.py` (patching both `kb.utils.io.atomic_text_write` AND `kb.capture.atomic_text_write`) collapses to a single-site patch of `kb.utils.io.atomic_text_write` only (since `kb.capture` no longer rebinds the symbol). `python -m pytest tests/test_capture.py -x` exits 0 with single-site patches.

### Vacuous-test upgrades (AC28-AC30)

**AC28.** `tests/test_models.py::test_graph_builder_documents_case_sensitivity_caveat` is **DELETED** (C43-vac-a). Behavior already covered by `test_page_id_*` in `test_utils.py`. Grepping for the test name in `tests/` returns no matches; `python -m pytest tests/test_models.py tests/test_utils.py -x` exits 0.

**AC29.** `tests/test_utils_io.py::test_load_page_frontmatter_docstring_documents_mtime_caveat` is **REPLACED** (C43-vac-b) by a behavioral test `test_load_page_frontmatter_mtime_collision` that:
1. Creates a temp wiki page (writes initial content via `atomic_text_write`).
2. Warms the LRU cache via `load_page_frontmatter`.
3. Uses `os.utime` to force identical coarse-resolution timestamps.
4. Overwrites the file with new content.
5. Calls `load_page_frontmatter` again.
6. Asserts the FRESH content is returned (not the stale cached version).

The new test must FAIL when the production cache-key logic is reverted to a pure mtime-keyed cache (per cycle-16 L2 self-check). `python -m pytest tests/test_utils_io.py::test_load_page_frontmatter_mtime_collision -xvs` passes; the old test name is absent from `tests/`.

**AC30.** In `tests/test_utils_io.py`, the `atomic_*_write` OneDrive docstring assertions from `test_cycle12_io_doc_caveats_are_present` are **DELETED** (redundant vs `test_sweep_orphan_tmp_*`). The `file_lock` PID-recycling portion is **REPLACED** by a behavioral test `test_file_lock_reaps_stale_lock_with_recycled_pid` that:
1. Creates a stale `.lock` file with a fake PID written into it.
2. Monkeypatches `psutil.pid_exists` to return `False` for that PID.
3. Acquires `file_lock` for the same target path.
4. Asserts successful acquisition (stale lock reaped).

The new test must FAIL when the production stale-lock-reaping logic is mutated to a no-op (per cycle-16 L2 self-check). `python -m pytest tests/test_utils_io.py::test_file_lock_reaps_stale_lock_with_recycled_pid -xvs` passes; no docstring assertions remain in `test_cycle12_io_doc_caveats_are_present` (or the test is deleted entirely).

---

## 4. Blast Radius

### Source modules modified or created

| File | Change |
|---|---|
| `src/kb/lint/checks.py` | **Removed** — replaced by `src/kb/lint/checks/` package |
| `src/kb/lint/checks/__init__.py` | **Created** — registry + re-exports for all former `checks.py` symbols (incl. `WIKI_DIR`/`RAW_DIR` constants for AC8) |
| `src/kb/lint/checks/frontmatter.py` | **Created** — frontmatter lint rules |
| `src/kb/lint/checks/dead_links.py` | **Created** — dead-link lint rules + `fix_dead_links` |
| `src/kb/lint/checks/orphan.py` | **Created** — orphan-page lint rules |
| `src/kb/lint/checks/cycles.py` | **Created** — cycle-detection lint rules |
| `src/kb/lint/checks/staleness.py` | **Created** — staleness checks |
| `src/kb/lint/checks/duplicate_slug.py` | **Created** — duplicate-slug lint rules |
| `src/kb/lint/checks/consistency.py` | **Created** — consistency lint rules |
| `src/kb/lint/checks/inline_callouts.py` | **Created** — inline callout lint rules |
| `src/kb/lint/augment.py` | **Removed** — replaced by `src/kb/lint/augment/` package |
| `src/kb/lint/_augment_manifest.py` | **Removed** — absorbed as `src/kb/lint/augment/manifest.py` |
| `src/kb/lint/_augment_rate.py` | **Removed** — absorbed as `src/kb/lint/augment/rate.py` |
| `src/kb/lint/augment/__init__.py` | **Created** — re-exports for all former `augment.py` symbols |
| `src/kb/lint/augment/collector.py` | **Created** |
| `src/kb/lint/augment/proposer.py` | **Created** |
| `src/kb/lint/augment/fetcher.py` | **Created** |
| `src/kb/lint/augment/persister.py` | **Created** |
| `src/kb/lint/augment/quality.py` | **Created** |
| `src/kb/lint/augment/manifest.py` | **Created** — uses lazy accessor (cycle-19 L2) |
| `src/kb/lint/augment/rate.py` | **Created** — uses lazy accessor (cycle-19 L2) |
| `src/kb/mcp/core.py` | **Reduced** — retains FastMCP app + helpers; target ≤ 300 LOC (≤ 350 with plan-gate justification) |
| `src/kb/mcp/ingest.py` | **Created** — ingest + capture MCP tools |
| `src/kb/mcp/compile.py` | **Created** — compile MCP tools |
| `src/kb/utils/io.py` | **Modified** — `atomic_text_write` gains `exclusive: bool = False` keyword-only parameter |
| `src/kb/capture.py` | **Modified** — removes `_exclusive_atomic_write`, imports from `kb.utils.io` |

### Tests modified or deleted

| File | Change |
|---|---|
| `tests/test_cycle12_sanitize_context.py` | **Deleted** — folded into `tests/test_mcp_core.py` (AC21) |
| `tests/test_mcp_core.py` | **Modified** — receives sanitize_context tests from AC21 fold |
| `tests/test_models.py` | **Modified** — `test_graph_builder_documents_case_sensitivity_caveat` deleted (AC28) |
| `tests/test_utils_io.py` | **Modified** — two vacuous tests replaced/deleted; two new behavioral tests added (AC29, AC30) |
| `tests/test_capture.py` | **Modified** — dual-site patches collapsed to single site (AC27) |
| `tests/test_cycle13_frontmatter_migration.py` | **Modified** — patch sites migrated to canonical submodule (C42-L3, AC14) |
| `tests/test_cycle17_resume.py` | **Modified** — patch sites migrated to canonical submodule (C42-L3, AC15) |

### Tests that must pass unchanged

The following files import from affected modules via stable paths and must pass without edits (`__init__.py` re-export shims handle compatibility):

- `tests/test_lint.py`, `tests/test_lint_runner.py`, `tests/test_lint_fix_v093.py`, `tests/test_fixes_v060.py`
- `tests/test_cycle9_lint_checks.py`, `tests/test_cycle9_lint_augment.py`, `tests/test_cycle5_hardening.py`
- `tests/test_cycle14_augment_key_order.py`
- `tests/test_cycle15_lint_authored_drift.py`, `tests/test_cycle15_lint_decay_wiring.py`, `tests/test_cycle15_lint_status_mature.py`
- `tests/test_cycle16_duplicate_slugs.py`, `tests/test_cycle16_inline_callouts.py`, `tests/test_cycle16_kb_query_save_as.py`
- `tests/test_cycle17_mcp_tool_coverage.py`
- `tests/test_compiler_mcp_v093.py`, `tests/test_cycle11_task6_mcp_ingest_type.py`
- `tests/test_backlog_by_file_cycle1.py`, `tests/test_backlog_by_file_cycle3.py`, `tests/test_backlog_by_file_cycle7.py`
- `tests/test_cli.py` — patches `kb.lint.checks.WIKI_DIR` / `RAW_DIR`; these MUST remain accessible at those paths after package split

### Re-export shim requirements (cycle-23 L5 + C42-L5)

All new `__init__.py` files MUST:

1. Re-export every symbol importable from the original flat module.
2. Use format: `from .submodule import symbol  # noqa: F401  # re-exported for backward compat (cycle-23 L5)`.
3. Be explicit per symbol (no implicit `__all__` substitution).
4. For module-level constants (`WIKI_DIR`, `RAW_DIR` in `lint/checks`), re-export at the package level so `monkeypatch.setattr(kb.lint.checks, "WIKI_DIR", ...)` continues to work.

### Monkeypatch migration requirement (C42-L3)

Before any symbol is moved to a new canonical module, the implementation plan MUST:

1. Grep for the symbol name in all `monkeypatch`/`patch(` sites in `tests/` using THREE shapes per cycle-19 L1:
   - String form: `rg "patch\(\"<module>\.<callable>\""`
   - Reference form via module variable: `rg "monkeypatch\.setattr\([^,]*,\s*\"<callable>\""`
   - Broader: `rg "setattr\([^,]*,\s*\"<callable>\""`
2. Identify every patch site and its current target string.
3. Update each patch to target the NEW canonical location (not the `__init__.py` re-export).

Known patch sites requiring migration (to verify in plan-gate Step 8):

- `tests/test_cycle13_frontmatter_migration.py` — `patch("kb.lint.augment.call_llm_json", ...)` sites
- `tests/test_cycle17_resume.py` — `patch("kb.lint.augment.run_augment", ...)` sites
- `tests/test_capture.py` — dual-site patches collapse to single site per AC27

---

## 5. Test Impact Summary

- **Source files modified/created/deleted:** 26 (3 deletes + 18 creates + 5 modifies).
- **Test files modified/deleted:** 7 (1 delete + 6 modifies).
- **Tests added (behavioral upgrades):** 2 net (AC29 + AC30 PID-recycle); AC28 is a delete; AC30 also deletes the docstring-assertion file portion. Net test count delta: roughly 0 to +2 (TBD post-implementation; verify via `pytest --collect-only | tail -1`).
- **Tests preserved unchanged:** ~25 listed in §4.
- **Risk-ordered implementation:** AC28-30 (vacuous upgrades, isolated) → AC21 (test fold) → M4 (atomic_text_write, smallest src) → M1 (checks split) → M2 (augment package) → M3 (mcp/core split, highest risk per cycle-23 L5).

---

## 6. Cycle-44 Provenance & Re-Verification

Cycle 44 was abandoned mid-Step 5 (DeepSeek R1 design-review prompt prepared but never dispatched). Cycle 45 reuses the cycle-44 requirements/threat-model/brainstorm content because:

1. The scope is unchanged (verified against `BACKLOG.md` 2026-04-27: Phase 4.6 MEDIUM/LOW + cycle-43 deferrals all still open).
2. LOC counts re-verified against current `src/kb/` (only `lint/augment.py` 1186→1189; ±0.3% drift, no change to scope).
3. The 4 open Dependabot alerts (3 litellm-blocked, 1 ragas-no-fix) and the pip-audit baseline are unchanged from cycle-44 baseline — captured fresh into `.data/cycle-45/`.
4. Test count is 3007 (matches cycle-43 baseline; baseline is current).

The Step-1 output is therefore primary-session adopted from cycle-44's prior Codex output — to be flagged in the Step-16 self-review as a primary-session shortcut per cycle-14 L1 / C37-L5 (operator holds full context after reading all 3 cycle-44 docs + BACKLOG + LOC verification + CVE refresh; Codex re-dispatch would produce ≥95% identical output for ~3 min wall-clock cost).

The cycle-44 worktree at `D:/Projects/llm-wiki-flywheel-c44` remains in place (its 3 untracked design docs are the source artifact) and will be removed at Step 15 cleanup or earlier if explicitly authorised.
