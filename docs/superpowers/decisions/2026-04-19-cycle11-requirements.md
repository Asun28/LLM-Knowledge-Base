# Cycle 11 — Requirements + Acceptance Criteria

**Date:** 2026-04-19
**Scope:** Backlog-by-file hardening. 14 items across 7 source/test files. Mostly test-coverage + small refactors + dead-path closure. No new features, no new MCP tools, no new dependencies.

## Problem

After cycle 10 closed the MCP wiki_dir validation + capture submission-time timestamp + extraction-string coercion items, the following open backlog issues remain and are small enough to group into a single cycle:

1. **Ingest pipeline silent-coerce gap.** Cycle 10 AC13a/AC13b applied `_coerce_str_field` at the pre-validation pass and `_build_summary_content`. 12+ other `.get()` read sites in `src/kb/ingest/pipeline.py` (lines 361, 384–386, 398, 411, 454–455, 947, 1001, 1017, 1115) still bypass the helper. A non-str (int, list, None) extraction field at these sites raises `AttributeError` / `TypeError` deep in the pipeline rather than a clean `ValueError` at the boundary.
2. **Ingest source type dead path.** `VALID_SOURCE_TYPES` accepts `"comparison"` and `"synthesis"` but `SOURCE_TYPE_DIRS` has no matching subdirs, so a caller passing `source_type="comparison"` to `ingest_source` takes a silent dead path through `_build_summary_content` that emits a near-empty summary. Backlog R4 item. Fix = reject early with a clear "use `kb_create_page` for comparison/synthesis pages" error.
3. **Graph helper misplacement.** `page_id` and `scan_wiki_pages` live in `kb.graph.builder` but are filesystem helpers, not graph primitives. 5 modules (`compile/linker`, `evolve/analyzer`, `lint/checks`, `lint/runner`, `lint/semantic`) import them from `graph.builder`; `utils/pages.py` already has a near-duplicate private `_page_id`. Backlog Phase 4.5 R1 MEDIUM item.
4. **CLI function-local import surface is untested.** `cli.py` intentionally keeps `from kb.X import Y` inside each command body so the `--version` short-circuit (cycle 7 AC30) can exit before `kb.config` imports. Import errors surface only on first invocation. Backlog R1 fix recommends a smoke test that exercises every command-import path — the safer option vs. the invasive "move to module top" which would break `--version`.
5. **Query-engine edge-case test gaps.** `_flag_stale_results` has three silent-skip branches (missing `sources`, non-ISO `updated`, mtime-equals-page-date) that are reachable in production but untested. Backlog cycle-4 R1 LOW item.
6. **Test scaffolding duplication.** `tests/test_ingest.py::test_ingest_source` at lines 86–163 manually builds wiki subdirs + index files + 6 `patch()` calls, duplicating what the `tmp_project` / `tmp_wiki` fixtures already provide. Backlog R3 MEDIUM item. Drift risk: when project scaffolding evolves, fixture-bypassing tests diverge silently.
7. **Signature-only monkeypatch regression test.** `tests/test_compile.py::test_compile_loop_does_not_double_write_manifest` counts `save_manifest` calls via `monkeypatch.setattr`. If `save_manifest` is renamed or relocated the count goes to 0 and the test passes silently. Backlog R6 LOW. Fix = add a second behavioural assertion on manifest file contents.
8. **Direct coverage gap for `page_id` + `scan_wiki_pages`.** The functions are only tested transitively via `build_graph`. A direct lookup (is the id lowercased? are hidden files skipped?) would catch regressions that graph-build error-swallowing masks. Backlog MEDIUM (`graph/builder.py` `page_id()` lowercasing — cross-platform issue R2 MEDIUM).

## Non-goals

- No new MCP tools.
- No new dependencies.
- No new frontmatter fields (`belief_state`, `status`, `authored_by` — deferred to a dedicated design cycle).
- No `save_as` / `kb_merge` / `kb_delete_source` / `kb_drift_audit` features.
- No coverage-confidence gate (new feature).
- No `CONTEXT_TIER_BUDGETS` proportional split (reshapes tier-budget ranking, deserves its own cycle).
- No two-phase compile pipeline, no atomic page-write-vs-evidence-append refactor, no concurrent-ingest manifest locks.
- No migrating `models/page.py` dataclasses into the pipeline return path (risky; deferred).
- No `graph/builder.py` `page_id()` lowercase fix for cross-platform filesystems (documented but deferred; would force a wiki-wide lowercase rename).
- No `comparison`/`synthesis` ingest support — we **close** the dead path (reject), not open it.

## Acceptance Criteria

Each AC is testable pass/fail.

### ingest/pipeline.py — defensive helper migration + dead-path closure (3 ACs)

- **AC1** — `_coerce_str_field` is called at *all* `extraction.get("<field>")` read sites whose callee expects a str. At minimum the 6 currently-unmigrated primary-text sites (title-merge path 947, key_claims 384/454, key_points 385/455, key_arguments 386, entities_mentioned 398/1001, concepts_mentioned 411/1017, optional authors 361, final-section key_claims 1115). **Test:** inject `extraction = {"title": 42, "key_claims": "oops-string-not-list", ...}` into `ingest_source` via `extraction=` kwarg and assert either (a) a clean `ValueError`/`TypeError` raised at pre-validation or (b) the coerced string is written verbatim without crashing deep in the pipeline. No site raises `AttributeError`.

- **AC2** — `ingest_source` returns `{"error": "...", "duplicate": False, ...}` or raises `ValueError` when called with `source_type="comparison"` or `source_type="synthesis"`, with an error message that names `kb_create_page` as the correct surface for those page types. No silent dead-path through `_build_summary_content`. **Test:** new `tests/test_cycle11_*.py::test_comparison_source_type_rejected` (+ synthesis variant) asserts the error path fires.

- **AC3** — Regression test in the cycle-11 test module pins `_coerce_str_field` public-contract: `None` → `""`, `int` → `str(int)`, `list` → joined comma-str, `bool` → `str(bool)`, already-str → unchanged. Prevents silent refactor regressions at the helper boundary.

### Graph helper relocation (3 ACs)

- **AC4** — `page_id(page_path, wiki_dir=None)` is defined in `src/kb/utils/pages.py` as the canonical location. The private `_page_id` helper in the same module is deleted (superseded by the public symbol; keep callers imported from `kb.utils.pages`). `kb.graph.builder.page_id` re-exports from `kb.utils.pages` for back-compat so existing `from kb.graph.builder import page_id` keeps working.

- **AC5** — `scan_wiki_pages(wiki_dir=None)` moves to `src/kb/utils/pages.py` alongside `page_id`. `kb.graph.builder.scan_wiki_pages` re-exports for back-compat. All 5 internal callers (`compile/linker`, `evolve/analyzer`, `lint/checks`, `lint/runner`, `lint/semantic`) switch to `from kb.utils.pages import ...` so the migration is complete at import sites we control; back-compat re-export covers external imports (there shouldn't be any in single-user scope but matters for tests pinning the old location).

- **AC6** — Direct test coverage for `page_id` and `scan_wiki_pages` at their canonical location. Test file: `tests/test_cycle11_utils_pages.py`. Cases: (a) `page_id` lowercases, (b) `page_id` preserves subdir separator, (c) `scan_wiki_pages` skips index sentinel files (`index.md`, `_sources.md`, `_categories.md`, `log.md`, `contradictions.md`, `purpose.md`, `hot.md`), (d) `scan_wiki_pages` returns deterministic sorted order for reproducibility.

### cli.py surface hardening (2 ACs)

- **AC7** — Smoke test in `tests/test_cycle11_cli_imports.py` exercises every CLI command's function-local import path: `ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`. For each, invoke `subprocess.run([sys.executable, "-m", "kb.cli", "<cmd>", "--help"], env={**os.environ, "PYTHONPATH": str(repo / "src")}, ...)` and assert `returncode == 0` + `"Usage:" in stdout`. Catches broken function-local imports at CI time rather than first-use time.

- **AC8** — Subprocess regression test pinning the cycle-7 AC30 contract: `python -m kb.cli --version` succeeds (returncode 0, "kb, version" in stdout) EVEN when `kb.config` import would fail. Implementation: in a subprocess test, monkeypatch-equivalent = prepend a PYTHONPATH entry containing a `kb/config.py` stub that raises at import time, and assert `--version` still exits 0. If straight monkeypatch is too brittle, at minimum assert the short-circuit short-path does not import `kb.config` (`'kb.config' not in sys.modules` after `cli.cli(['--version'])` from a fresh subprocess via `python -c`).

### Query engine edge-case test coverage (3 ACs)

- **AC9** — Test `_flag_stale_results` returns `stale=False` when result dict has `updated` but no `sources` key (empty list or missing). Current code's `if not updated_str or not sources: continue` path, previously untested.

- **AC10** — Test `_flag_stale_results` returns `stale=False` when `updated` is non-ISO (e.g. `"yesterday"`, `"04/19/2026"`, `""`, non-str `int`). Current `date.fromisoformat(...)` `except (ValueError, TypeError)` path.

- **AC11** — Test `_flag_stale_results` returns `stale=False` when newest source mtime **equals** the page's `updated` date (strict `>`, not `>=`). Prevents the off-by-one where same-day edits flip to stale.

### Test scaffolding cleanup (2 ACs)

- **AC12** — `tests/test_ingest.py::test_ingest_source` replaces its manual wiki-subdir scaffolding + 5-way `patch()` block (current lines ~86–163) with the `tmp_project` fixture and passes `wiki_dir=tmp_project/"wiki"` + `raw_dir=tmp_project/"raw"` explicitly to `ingest_source`. No functional behavior change; only the test setup shrinks.

- **AC13** — `tests/test_compile.py::test_compile_loop_does_not_double_write_manifest` gains a second assertion that does NOT depend on module-level `monkeypatch.setattr(..., save_manifest, ...)`. Option A: assert `manifest_path.stat().st_mtime_ns` changes exactly once per ingest call (requires synchronising timing). Option B (preferred): load the manifest file before and after `compile_wiki` and assert the key-count / per-key hashes match the single-source contract (i.e. re-running the same compile does NOT mutate the manifest beyond the expected entries).

### Config / CHANGELOG alignment (1 AC)

- **AC14** — `CHANGELOG.md` `[Unreleased]` gains a cycle-11 block documenting: items closed (AC1–AC13), any deferred items re-surfaced, new test-file list. `BACKLOG.md` deletes the resolved items (R1 graph helper, R4 comparison/synthesis dead path, R6 monkeypatch-only regression test, R1/R3 scaffolding duplication, R1 edge-case test gaps) and updates the Phase 4.5 MEDIUM counts.

## Blast radius (modules touched)

| Module | Change | Risk |
|---|---|---|
| `src/kb/ingest/pipeline.py` | Insert `_coerce_str_field(extraction, field)` at 6+ read sites; add `source_type in {comparison, synthesis}` reject-early guard | Low — helper is additive; reject is a new error path for a currently broken surface |
| `src/kb/graph/builder.py` | Convert `page_id` + `scan_wiki_pages` to re-exports from `kb.utils.pages` | Low — back-compat preserved via re-export |
| `src/kb/utils/pages.py` | Absorb canonical `page_id` + `scan_wiki_pages`; delete private `_page_id` duplicate | Low — single-source-of-truth refactor |
| `src/kb/compile/linker.py` | Switch `from kb.graph.builder import page_id, scan_wiki_pages` → `from kb.utils.pages import ...` | Low — import-site change |
| `src/kb/evolve/analyzer.py` | Same import-site swap | Low |
| `src/kb/lint/checks.py` | Same import-site swap | Low |
| `src/kb/lint/runner.py` | Same import-site swap | Low |
| `src/kb/lint/semantic.py` | Same import-site swap | Low |
| `tests/test_ingest.py` | Replace manual scaffolding with `tmp_project` | Low — behavior-preserving test refactor |
| `tests/test_compile.py` | Add behavioural assertion to existing test | Low — pure additive assertion |
| `tests/test_cycle11_ingest_coerce.py` (new) | AC1 + AC2 + AC3 | Low — test-only |
| `tests/test_cycle11_utils_pages.py` (new) | AC6 | Low — test-only |
| `tests/test_cycle11_cli_imports.py` (new) | AC7 + AC8 | Low — subprocess smoke tests |
| `tests/test_cycle11_stale_results.py` (new) | AC9 + AC10 + AC11 | Low — test-only |
| `CHANGELOG.md`, `BACKLOG.md` | AC14 | Low — docs |

## Dependencies between ACs

- AC4 + AC5 must land before AC6 (test targets the canonical location).
- AC4/AC5 caller-migration (5 modules) must land in same commit as the `kb.graph.builder` re-export to avoid an import-broken intermediate commit.
- AC1 (helper migration) independent of AC2 (reject comparison/synthesis).
- AC7/AC8 (cli smoke) independent of everything else.
- AC9/AC10/AC11 (stale-results edge cases) independent of everything.
- AC12/AC13 (test cleanup) independent.
- AC14 (docs) last.

## Per-file commit plan (batch-by-file convention)

One commit per file (per user's `feedback_batch_by_file` memory). Order:

1. `src/kb/utils/pages.py` — AC4 + AC5 canonical absorb + delete duplicate (single file).
2. `src/kb/graph/builder.py` — convert to re-export shim (single file).
3. `src/kb/compile/linker.py` + `src/kb/evolve/analyzer.py` + `src/kb/lint/checks.py` + `src/kb/lint/runner.py` + `src/kb/lint/semantic.py` — caller-migration cluster (SAME commit — atomic import-site swap required by AC4/AC5 dependency; justified cluster per cycle-4 RedFlag).
4. `src/kb/ingest/pipeline.py` — AC1 + AC2 migration + reject guard (single file).
5. `tests/test_ingest.py` — AC12 scaffolding cleanup.
6. `tests/test_compile.py` — AC13 behavioural assertion.
7. `tests/test_cycle11_utils_pages.py` — AC6.
8. `tests/test_cycle11_cli_imports.py` — AC7 + AC8.
9. `tests/test_cycle11_stale_results.py` — AC9 + AC10 + AC11.
10. `tests/test_cycle11_ingest_coerce.py` — AC1 + AC2 + AC3 regression tests.
11. `CHANGELOG.md` + `BACKLOG.md` — AC14.

## Test-count delta target

Baseline (post-cycle-10 merge): 2041 passing.
Expected: 2041 → 2060+ (at least 15 new tests, one per AC where AC is a test target; more where AC has multiple edge cases).

## Security baseline reference

Defer to Step 2 snapshot. Step 2 will capture `gh api dependabot/alerts` + `pip-audit` baselines matching cycle-10's process.
