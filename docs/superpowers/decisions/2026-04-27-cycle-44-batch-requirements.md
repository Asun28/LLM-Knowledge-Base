# Cycle 44 Batch Requirements

**Date:** 2026-04-27
**Branch:** cycle-44-batch
**Scope:** Phase 4.6 close (4 MEDIUM + 1 LOW) + cycle-43 carry-overs (AC10 fold + 3 vacuous-test upgrades)

---

## 1. Problem

### M1 --- lint/checks.py monolith (1046 LOC)

As cited verbatim from BACKLOG.md Phase 4.6 MEDIUM: `lint/checks.py` (1046 LOC) --- frontmatter, dead-link, orphan, cycle-detection, staleness, and duplicate-slug rules all live in one file. Cycle-30 added consistency lint, cycle-31 added deep-lint --- every new rule grows the same module, defeating per-rule test isolation. The suggested fix: split into `lint/checks/<rule>.py` per rule + `lint/checks/__init__.py` registry; or `lint/rules/` matching `lint/runner.py` dispatch contract. With 1046 lines housing all check functions, every new rule adds to an already-overloaded file, and tests cannot import a single rule file in isolation.

### M2 --- lint/augment.py monolith (1189 LOC) + L1 siblings

As cited from BACKLOG.md Phase 4.6 MEDIUM: `lint/augment.py` (1186 LOC) --- collector, proposer, URL fetcher, persister, outcome recorder, post-ingest quality. The dual `_augment_manifest.py` (213 LOC) and `_augment_rate.py` (110 LOC) sibling helpers further confirm the file is at-or-past the natural decomposition point. The fix: convert `lint/augment.py` to `lint/augment/` package with `collector.py` / `proposer.py` / `fetcher.py` / `persister.py` / `quality.py`; absorb `_augment_manifest.py` and `_augment_rate.py` as `manifest.py` and `rate.py` inside the new package --- covers Phase 4.6 LOW item below. This simultaneously closes Phase 4.6 LOW: `lint/_augment_manifest.py` (213 LOC) and `lint/_augment_rate.py` (110 LOC) --- leading-underscore private siblings used only by `lint/augment.py`. The leading underscore on a top-level file (vs a function) is non-standard Python; either inline or promote to public submodules.

### M3 --- mcp/core.py monolith (1149 LOC)

As cited from BACKLOG.md Phase 4.6 MEDIUM: `mcp/core.py` (1149 LOC) --- query, ingest, capture, compile, and helper-tool implementations co-resident despite the cycle-4-13 split that already moved browse / health / quality out. Adding any Phase 5 write-path tool (`kb_review_page` etc., open in Phase 4.5 MEDIUM) lands here by default. The fix: continue the cycle-4-13 pattern --- add `mcp/ingest.py`, `mcp/compile.py`; keep `core.py` for the FastMCP app + cross-cutting helpers <=300 LOC.

### M4 --- Dual atomic-write helpers

As cited from BACKLOG.md Phase 4.6 MEDIUM: `capture.py:461` `_exclusive_atomic_write` and `utils/io.py:144` `atomic_text_write` are two write-helpers with different invariants --- capture uses `O_EXCL` for slug-collision detection, utils uses tempfile+rename for crash-atomicity. Cycle 38 AC6 widened test-side patching to cover both sites but the duplication itself was not collapsed; any future write-discipline change (e.g. `fsync` parent dir, lock acquisition) must be applied twice. The fix: single `atomic_text_write(path, content, *, exclusive=False)` in `utils/io.py` accepting both modes; capture.py imports it; cycle-38 dual-site test patches collapse to a single patch. Per cycle-15 L1, the unified function must preserve the full contract of both predecessors: crash-atomicity (tempfile+rename) for `exclusive=False` and `O_EXCL` slug-collision detection for `exclusive=True`.

### Cycle-43 Carry-Overs --- AC10 fold + 3 vacuous-test upgrades

The BACKLOG.md cycle-43 deferral note states: `tests/test_cycle12_sanitize_context.py` to `tests/test_mcp_core.py` postponed due to active cycle-42 Phase 4.6 dedup interference. The `_sanitize_conversation_context` symbol survives cycle-42, but co-location with cycle-42 surrounding `mcp/core.py` edits creates merge surface. Revisit in cycle 44+ once cycle-42 lands. Commit `eee0e5c` is the post-cycle-43 head; the merge surface is now clear.

The three vacuous-test upgrade candidates (flagged as C40-L3 + C41-L1 in BACKLOG.md) are:
1. `tests/test_models.py::test_graph_builder_documents_case_sensitivity_caveat` --- docstring-content assertion; upgrade path is DELETE (behavior already covered by `test_page_id_*` in `test_utils.py`).
2. `tests/test_utils_io.py::test_load_page_frontmatter_docstring_documents_mtime_caveat` --- docstring-content assertion; upgrade path is replacement with a behavioral mtime-collision test.
3. `tests/test_utils_io.py::test_cycle12_io_doc_caveats_are_present` --- docstring-content assertion; upgrade path is DELETE the `atomic_*_write` portion (redundant vs `test_sweep_orphan_tmp_*`) and add a behavioral PID-recycling test for `file_lock`.

---

## 2. Non-Goals

- **NO functional or behavior changes.** Every item in this cycle is a pure structural refactor (file splits, package conversions, helper consolidation) or a test-quality upgrade. Observable behavior of all public APIs and all CLI/MCP tool outputs is preserved unchanged.
- **NO Phase 5 items touched.** Phase 5 features (community proposals, inline claim tags, URL-aware ingest, semantic chunking, autonomous research loop, etc.) are explicitly out of scope.
- **NO new lint rules.** The checks.py split creates per-rule files for existing rules only; no new checking logic is added.
- **NO changes to public CLI or MCP tool surface.** All 29 MCP tool names and all 24 CLI subcommands are preserved as-is.
- **NO renames of tested public functions.** `check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `fix_dead_links`, `run_augment`, `save_page_frontmatter`, `_build_proposer_prompt`, `_format_proposals_md`, `atomic_text_write`, `kb_compile`, `kb_query`, `kb_ingest`, `_sanitize_conversation_context`, and all other named public symbols remain importable from their current paths.
- Per **cycle-23 L5:** Package `__init__.py` files MUST preserve `from <package> import <symbol>` semantics for any caller. Re-export shims are required in every new `__init__.py`.
- Per **C42-L5:** All re-export lines in `__init__.py` files must carry an explicit `# noqa: F401` comment and a one-sentence explanation comment to prevent `ruff --fix` from stripping them.
- Per **C42-L3:** Function moves invalidate monkeypatch.setattr even when the function is re-exported. Patch sites must be migrated to target the NEW canonical module. The implementation plan must grep all current monkeypatch/patch( sites BEFORE moving any module-global symbol.
- Per **cycle-15 L1:** Any AC that says replace existing X with Y must explicitly note that Y preserves X full contract (both crash-atomicity and O_EXCL semantics for M4).
- Per **cycle-19 L2:** Module-top file reads must become lazy `_get_X()` accessors when the module participates in a reload cascade. Applies to `lint/augment/manifest.py` and `lint/augment/rate.py`.

---

## 3. Acceptance Criteria

### M1 --- checks.py split (AC1-AC10)

**AC1.** `src/kb/lint/checks/` package directory exists containing an `__init__.py` registry file. The original `src/kb/lint/checks.py` flat file is removed. Importing `kb.lint.checks` succeeds without error.

**AC2.** Each lint rule group has its own sub-module file. At minimum the following files exist: `src/kb/lint/checks/frontmatter.py`, `src/kb/lint/checks/dead_links.py`, `src/kb/lint/checks/orphan.py`, `src/kb/lint/checks/cycles.py`, `src/kb/lint/checks/staleness.py`, `src/kb/lint/checks/duplicate_slug.py`, `src/kb/lint/checks/consistency.py`, `src/kb/lint/checks/inline_callouts.py`. Assertion: each file exists on disk and contains at least one function definition.

**AC3.** `src/kb/lint/checks/__init__.py` re-exports every function importable from the original `kb.lint.checks` flat module. Target symbols include at minimum: `check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `fix_dead_links`, plus any other top-level callable. Each re-export line carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`. Assertion: `from kb.lint.checks import check_source_coverage` resolves to the function object in the submodule.

**AC4.** `tests/test_lint.py` passes without modification. Assertion: `python -m pytest tests/test_lint.py -x` exits 0.

**AC5.** `tests/test_backlog_by_file_cycle1.py`, `tests/test_backlog_by_file_cycle3.py`, `tests/test_backlog_by_file_cycle7.py` pass without modification (import `from kb.lint.checks import check_source_coverage` and `from kb.lint import checks`). Assertion: `python -m pytest tests/test_backlog_by_file_cycle1.py tests/test_backlog_by_file_cycle3.py tests/test_backlog_by_file_cycle7.py -x` exits 0.

**AC6.** `tests/test_cycle15_lint_authored_drift.py`, `tests/test_cycle15_lint_decay_wiring.py`, `tests/test_cycle15_lint_status_mature.py` pass without modification. Assertion: `python -m pytest tests/test_cycle15_lint_authored_drift.py tests/test_cycle15_lint_decay_wiring.py tests/test_cycle15_lint_status_mature.py -x` exits 0.

**AC7.** `tests/test_cycle16_duplicate_slugs.py` and `tests/test_cycle16_inline_callouts.py` pass without modification. Assertion: `python -m pytest tests/test_cycle16_duplicate_slugs.py tests/test_cycle16_inline_callouts.py -x` exits 0.

**AC8.** `tests/test_cli.py` passes without modification. This file patches `kb.lint.checks.WIKI_DIR` and `kb.lint.checks.RAW_DIR`; those module-level attributes must remain accessible at `kb.lint.checks.WIKI_DIR` / `RAW_DIR` after the package split. Assertion: `python -m pytest tests/test_cli.py -x` exits 0.

**AC9.** `tests/test_fixes_v060.py` and `tests/test_lint_fix_v093.py` pass without modification. Assertion: `python -m pytest tests/test_fixes_v060.py tests/test_lint_fix_v093.py -x` exits 0.

**AC10.** `tests/test_lint_runner.py` passes without modification. Assertion: `python -m pytest tests/test_lint_runner.py -x` exits 0.

### M2 --- augment.py package conversion (AC11-AC18)

**AC11.** `src/kb/lint/augment/` package directory exists containing `__init__.py`, `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py`. The original `src/kb/lint/augment.py`, `src/kb/lint/_augment_manifest.py`, and `src/kb/lint/_augment_rate.py` are removed. Assertion: all 8 new files exist; all 3 removed files are absent.

**AC12.** `src/kb/lint/augment/__init__.py` re-exports every symbol importable from the original flat `kb.lint.augment` module. Target symbols include at minimum: `run_augment`, `save_page_frontmatter`, `_build_proposer_prompt`, `_format_proposals_md`. Each re-export line carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`. Assertion: `from kb.lint.augment import run_augment` and `from kb.lint.augment import _build_proposer_prompt` each resolve to the correct function.

**AC13.** `manifest.py` and `rate.py` inside the package do NOT perform module-top disk reads (per cycle-19 L2). Any JSON state previously loaded at import time must be wrapped in a lazy `_get_X()` accessor called on first use. Assertion: importing `kb.lint.augment` with no wiki directory configured does not raise `FileNotFoundError` or perform disk I/O.

**AC14.** Monkeypatch patch sites in `tests/test_cycle13_frontmatter_migration.py` (`patch(chr(34) + chr(107) + chr(98) + chr(46) + chr(108) + chr(105) + chr(110) + chr(116) + chr(46) + chr(97) + chr(117) + chr(103) + chr(109) + chr(101) + chr(110) + chr(116) + chr(46) + chr(99) + chr(97) + chr(108) + chr(108) + chr(95) + chr(108) + chr(108) + chr(109) + chr(95) + chr(106) + chr(115) + chr(111) + chr(110) + chr(34) + chr(44) + chr(32) + chr(46) + chr(46) + chr(46) + chr(41)`) are updated to patch `call_llm_json` at its NEW canonical module location. Per C42-L3, the patch target must be the owner module. Assertion: all `test_cycle13_frontmatter_migration.py` tests pass.

**AC15.** Monkeypatch patch sites in `tests/test_cycle17_resume.py` (`patch(chr(34) + chr(107) + chr(98) + chr(46) + chr(108) + chr(105) + chr(110) + chr(116) + chr(46) + chr(97) + chr(117) + chr(103) + chr(109) + chr(101) + chr(110) + chr(116) + chr(46) + chr(114) + chr(117) + chr(110) + chr(95) + chr(97) + chr(117) + chr(103) + chr(109) + chr(101) + chr(110) + chr(116) + chr(34) + chr(44) + chr(32) + chr(46) + chr(46) + chr(46) + chr(41)`) are updated to target the canonical module. Assertion: all `test_cycle17_resume.py` tests pass.

**AC16.** `tests/test_backlog_by_file_cycle1.py`, `tests/test_cycle9_lint_augment.py`, `tests/test_cycle5_hardening.py` pass without modification. Assertion: `python -m pytest tests/test_backlog_by_file_cycle1.py tests/test_cycle9_lint_augment.py tests/test_cycle5_hardening.py -x` exits 0.

**AC17.** `tests/test_cycle14_augment_key_order.py` passes without modification. Assertion: `python -m pytest tests/test_cycle14_augment_key_order.py -x` exits 0.

**AC18.** Full lint test suite passes: `python -m pytest tests/test_lint.py tests/test_cycle13_frontmatter_migration.py tests/test_cycle14_augment_key_order.py tests/test_cycle15_lint_authored_drift.py tests/test_cycle15_lint_decay_wiring.py tests/test_cycle15_lint_status_mature.py -x` exits 0.

### M3 --- mcp/core.py split (AC19-AC24)

**AC19.** `src/kb/mcp/ingest.py` and `src/kb/mcp/compile.py` are created. Ingest-related tool implementations (`kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_capture`, `kb_compile_scan`) move to `ingest.py`. Compile-related implementations (`kb_compile` and compile-specific helpers) move to `compile.py`. `core.py` retains only the FastMCP app instance, cross-cutting helpers, and `_sanitize_conversation_context`; its line count must be <=300 LOC after the split. Assertion: line count of `src/kb/mcp/core.py` is <=300.

**AC20.** Re-exports in `core.py` preserve `from kb.mcp.core import kb_ingest`, `from kb.mcp.core import kb_compile`, `from kb.mcp.core import _sanitize_conversation_context` for all existing callers. Assertion: both `from kb.mcp.core import kb_compile` and `from kb.mcp.core import kb_ingest` succeed without `ImportError`.

**AC21.** The AC10 carry-over fold is complete: `tests/test_cycle12_sanitize_context.py` is deleted and its tests are merged into `tests/test_mcp_core.py`. The folded tests cover at minimum: empty list input, list-over-limit truncation, and context content passthrough for `_sanitize_conversation_context`. Assertion: `tests/test_cycle12_sanitize_context.py` does not exist; `python -m pytest tests/test_mcp_core.py -x -k sanitize` passes with >=5 tests collected.

**AC22.** `tests/test_compiler_mcp_v093.py` passes without modification (`from kb.mcp.core import kb_compile` + inline `from kb.mcp.core import kb_query`). Assertion: `python -m pytest tests/test_compiler_mcp_v093.py -x` exits 0.

**AC23.** `tests/test_cycle11_task6_mcp_ingest_type.py` and `tests/test_cycle17_mcp_tool_coverage.py` pass without modification. Assertion: `python -m pytest tests/test_cycle11_task6_mcp_ingest_type.py tests/test_cycle17_mcp_tool_coverage.py -x` exits 0.

**AC24.** `tests/test_cycle16_kb_query_save_as.py` passes without modification (`from kb.mcp import core as mcp_core`). Assertion: `python -m pytest tests/test_cycle16_kb_query_save_as.py -x` exits 0.

### M4 --- atomic_text_write consolidation (AC25-AC27)

**AC25.** `src/kb/utils/io.py::atomic_text_write` gains an `exclusive: bool = False` keyword parameter. When `exclusive=True`, uses `os.open(..., os.O_CREAT | os.O_EXCL | os.O_WRONLY)` for slug-collision detection (raises `FileExistsError` on conflict). When `exclusive=False` (default), uses the existing tempfile+rename crash-atomicity path. Function signature: `def atomic_text_write(path: Path | str, content: str, *, exclusive: bool = False) -> None`. Per cycle-15 L1, both contracts are preserved. Assertion: calling `atomic_text_write(existing_path, chr(34) + chr(120) + chr(34) + chr(44) + chr(32) + chr(101) + chr(120) + chr(99) + chr(108) + chr(117) + chr(115) + chr(105) + chr(118) + chr(101) + chr(61) + chr(84) + chr(114) + chr(117) + chr(101) + chr(41)` raises `FileExistsError`; calling with `exclusive=False` to a new path succeeds.

**AC26.** `src/kb/capture.py` removes its internal `_exclusive_atomic_write` helper and instead calls `atomic_text_write(..., exclusive=True)` imported from `kb.utils.io`. Assertion: `grep chr(34) + chr(95) + chr(101) + chr(120) + chr(99) + chr(108) + chr(117) + chr(115) + chr(105) + chr(118) + chr(101) + chr(95) + chr(97) + chr(116) + chr(111) + chr(109) + chr(105) + chr(99) + chr(95) + chr(119) + chr(114) + chr(105) + chr(116) + chr(101) + chr(34) + chr(32) + chr(115) + chr(114) + chr(99) + chr(47) + chr(107) + chr(98) + chr(47) + chr(99) + chr(97) + chr(112) + chr(116) + chr(117) + chr(114) + chr(101) + chr(46) + chr(112) + chr(121)` returns no matches; `python -c chr(34) + chr(102) + chr(114) + chr(111) + chr(109) + chr(32) + chr(107) + chr(98) + chr(46) + chr(99) + chr(97) + chr(112) + chr(116) + chr(117) + chr(114) + chr(101) + chr(32) + chr(105) + chr(109) + chr(112) + chr(111) + chr(114) + chr(116) + chr(32) + chr(67) + chr(97) + chr(112) + chr(116) + chr(117) + chr(114) + chr(101) + chr(82) + chr(101) + chr(115) + chr(117) + chr(108) + chr(116) + chr(34)` succeeds.

**AC27.** The dual-site monkeypatch in `tests/test_capture.py` (patching both `kb.utils.io.atomic_text_write` AND `kb.capture.atomic_text_write`) collapses to a single-site patch of `kb.utils.io.atomic_text_write` only. Assertion: `python -m pytest tests/test_capture.py -x` exits 0 with single-site patches.

### Vacuous-test upgrades (AC28-AC30)

**AC28.** (C43-vac-a) `tests/test_models.py::test_graph_builder_documents_case_sensitivity_caveat` is DELETED. Assertion: grepping for test_graph_builder_documents_case_sensitivity_caveat in tests/ returns no matches; `python -m pytest tests/test_models.py tests/test_utils.py -x` exits 0.

**AC29.** (C43-vac-b) `tests/test_utils_io.py::test_load_page_frontmatter_docstring_documents_mtime_caveat` is REPLACED by a behavioral test `test_load_page_frontmatter_mtime_collision` that: creates a temp wiki page, writes initial content, warms the cache via `load_page_frontmatter`, uses `os.utime` to force identical coarse-resolution timestamps, overwrites the file with new content, calls `load_page_frontmatter` again, and asserts the FRESH content is returned (not the stale cached version). Assertion: `python -m pytest tests/test_utils_io.py::test_load_page_frontmatter_mtime_collision -xvs` passes; the old test name is absent.

**AC30.** (C43-vac-c) In `tests/test_utils_io.py`, the `atomic_*_write` OneDrive docstring assertions from `test_cycle12_io_doc_caveats_are_present` are DELETED (redundant vs `test_sweep_orphan_tmp_*`). The `file_lock` PID-recycling portion is REPLACED by a behavioral test `test_file_lock_reaps_stale_lock_with_recycled_pid` that: creates a stale `.lock` file with a fake PID, monkeypatches `psutil.pid_exists` to return `False` for that PID, acquires the `file_lock`, and asserts successful acquisition (stale lock reaped). Assertion: `python -m pytest tests/test_utils_io.py::test_file_lock_reaps_stale_lock_with_recycled_pid -xvs` passes; no docstring assertions remain in `test_cycle12_io_doc_caveats_are_present` (or the test is deleted entirely).

---

## 4. Blast Radius

### Source modules modified or created

| File | Change |
|---|---|
| `src/kb/lint/checks.py` | **Removed** --- replaced by `src/kb/lint/checks/` package |
| `src/kb/lint/checks/__init__.py` | **Created** --- registry + re-exports for all former `checks.py` symbols |
| `src/kb/lint/checks/frontmatter.py` | **Created** --- frontmatter lint rules |
| `src/kb/lint/checks/dead_links.py` | **Created** --- dead-link lint rules + `fix_dead_links` |
| `src/kb/lint/checks/orphan.py` | **Created** --- orphan-page lint rules |
| `src/kb/lint/checks/cycles.py` | **Created** --- cycle-detection lint rules |
| `src/kb/lint/checks/staleness.py` | **Created** --- staleness checks |
| `src/kb/lint/checks/duplicate_slug.py` | **Created** --- duplicate-slug lint rules |
| `src/kb/lint/checks/consistency.py` | **Created** --- consistency lint rules |
| `src/kb/lint/checks/inline_callouts.py` | **Created** --- inline callout lint rules |
| `src/kb/lint/augment.py` | **Removed** --- replaced by `src/kb/lint/augment/` package |
| `src/kb/lint/_augment_manifest.py` | **Removed** --- absorbed as `src/kb/lint/augment/manifest.py` |
| `src/kb/lint/_augment_rate.py` | **Removed** --- absorbed as `src/kb/lint/augment/rate.py` |
| `src/kb/lint/augment/__init__.py` | **Created** --- re-exports for all former `augment.py` symbols |
| `src/kb/lint/augment/collector.py` | **Created** --- collection logic |
| `src/kb/lint/augment/proposer.py` | **Created** --- LLM proposer logic |
| `src/kb/lint/augment/fetcher.py` | **Created** --- URL fetch logic |
| `src/kb/lint/augment/persister.py` | **Created** --- persistence logic |
| `src/kb/lint/augment/quality.py` | **Created** --- post-ingest quality logic |
| `src/kb/lint/augment/manifest.py` | **Created** --- from `_augment_manifest.py`; uses lazy accessor (cycle-19 L2) |
| `src/kb/lint/augment/rate.py` | **Created** --- from `_augment_rate.py`; uses lazy accessor (cycle-19 L2) |
| `src/kb/mcp/core.py` | **Reduced** --- retains FastMCP app + helpers; target <=300 LOC |
| `src/kb/mcp/ingest.py` | **Created** --- ingest + capture MCP tools |
| `src/kb/mcp/compile.py` | **Created** --- compile MCP tools |
| `src/kb/utils/io.py` | **Modified** --- `atomic_text_write` gains `exclusive: bool = False` |
| `src/kb/capture.py` | **Modified** --- removes `_exclusive_atomic_write`, imports from `kb.utils.io` |

### Tests modified or deleted

| File | Change |
|---|---|
| `tests/test_cycle12_sanitize_context.py` | **Deleted** --- folded into `tests/test_mcp_core.py` (AC21) |
| `tests/test_mcp_core.py` | **Modified** --- receives sanitize_context tests from AC21 fold |
| `tests/test_models.py` | **Modified** --- `test_graph_builder_documents_case_sensitivity_caveat` deleted (AC28) |
| `tests/test_utils_io.py` | **Modified** --- two vacuous tests replaced/deleted; two new behavioral tests added (AC29, AC30) |
| `tests/test_capture.py` | **Modified** --- dual-site patches collapsed to single site (AC27) |
| `tests/test_cycle13_frontmatter_migration.py` | **Modified** --- patch sites migrated to canonical submodule (C42-L3, AC14) |
| `tests/test_cycle17_resume.py` | **Modified** --- patch sites migrated to canonical submodule (C42-L3, AC15) |

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
- `tests/test_cli.py` --- patches `kb.lint.checks.WIKI_DIR` / `RAW_DIR`; these must remain accessible at those paths after package split

### Re-export shim requirements (cycle-23 L5 + C42-L5)

All new `__init__.py` files must:
1. Re-export every symbol importable from the original flat module.
2. Use format: `from .submodule import symbol` with `# noqa: F401  # re-exported for backward compat (cycle-23 L5)` comment.
3. Be explicit per symbol (no implicit `__all__` substitution).
4. For module-level constants (e.g., `WIKI_DIR`, `RAW_DIR` in checks), re-export at the package level so monkeypatch.setattr of `kb.lint.checks.WIKI_DIR` continues to work.

### Monkeypatch migration requirement (C42-L3)

Before any symbol is moved to a new canonical module, the implementation plan must:
1. Grep for the symbol name in all monkeypatch/patch( sites in tests/.
2. Identify every patch site and its current target string.
3. Update each patch to target the new canonical location (not the `__init__.py` re-export).

Known patch sites requiring migration:
- `tests/test_cycle13_frontmatter_migration.py:531,551,643,663` --- patch(kb.lint.augment.call_llm_json, ...)
- `tests/test_cycle17_resume.py:123,168` --- patch(kb.lint.augment.run_augment, ...)
- `tests/test_capture.py:805-806,819-820` --- dual-site patches collapse to single site per AC27
