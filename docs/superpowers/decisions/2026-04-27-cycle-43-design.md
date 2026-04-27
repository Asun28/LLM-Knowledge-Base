# Cycle 43 — Step 5 Design Decision Gate

**Date:** 2026-04-27
**Inputs:** R1 DeepSeek V4 Pro (`.data/cycle-43/c43-step4-r1-deepseek.txt`), R2 Codex (background-task transcript), per-file reads of all 12 fold candidates.

## VERDICT: APPROVE-WITH-CONDITIONS

11 folds proceed; 1 AC defers to cycle 44 due to cycle-42 collision risk; 4 BACKLOG entries filed for vacuous-test components per C40-L3.

## DECISIONS (resolution of every open question)

### Q1 — AC10 cycle-42 collision risk

**Question:** test_cycle12_sanitize_context.py imports `kb.mcp.core` + `kb.query.engine` and uses `core._sanitize_conversation_context`. Cycle-42 modifies BOTH src/kb/mcp/core.py (commit aa43d4e) AND src/kb/query/engine.py (commit 0ef8843). Even if `_sanitize_conversation_context` itself is unchanged, the surrounding module state may produce merge conflicts.

**OPTIONS:**
- A: Fold into `test_mcp_core.py` (closest semantic home) — risks conflict with cycle-42's mcp/core.py edits.
- B: Fold into `test_utils.py` — wrong home (test is about MCP-level sanitization, not utils).
- C: Defer to cycle 44, file BACKLOG entry.

**ANALYSIS:** A would force me to merge into `test_mcp_core.py` while cycle-42 is actively editing surrounding tests. The `_sanitize_conversation_context` symbol survives cycle-42 (grep confirmed), but adjacent test infrastructure changes from cycle-42 (test_v01013_cli_error_truncation.py, mcp/* test patches) increase merge surface. B is wrong home — defeats the canonical-home rule. C costs one cycle's delay but eliminates the conflict.

**DECISION:** **C — defer AC10 to cycle 44.** File a BACKLOG.md entry under Phase 4.5 HIGH #4 progress note: "AC10 (test_cycle12_sanitize_context.py → test_mcp_core.py) deferred from cycle 43 due to active cycle-42 mcp/* dedup; revisit cycle 44+." Confidence: HIGH.

### Q2 — AC1 host file's pre-existing _sanitize_error_str import

**Question:** test_mcp_browse_health.py:20 already imports `_sanitize_error_str` (the symbol cycle-42 is removing). Codex R2 flagged this as a NEEDS-INVESTIGATION concern: "the alias survives only if cycle-42's removal stays stashed."

**ANALYSIS:** This is **cycle-42's problem, not mine.** Cycle-42's commit aa43d4e removes `_sanitize_error_str` and aliases it via `sanitize_error_text`. test_mcp_browse_health.py:20's import will break when cycle-42 lands — but that's cycle-42's responsibility to fix in their test-update sweep. My AC1 fold (`test_cycle10_browse.py` → `test_mcp_browse_health.py`) does NOT add a new `_sanitize_error_str` import; it adds a single test that uses `browse.kb_read_page` directly. The fold is therefore safe.

**DECISION:** **APPROVE AC1 fold.** Add a brief comment in the new test class noting that the fold is safe because the new test does not add new cycle-42-affected imports. Confidence: HIGH.

### Q3 — AC4 canonical home (test_paths.py vs test_models.py)

**Question:** `test_cycle11_conftest_fixture.py` has ONE test verifying `tmp_project` fixture creates canonical wiki files (index.md, _sources.md, log.md) with expected content. Where does this fixture-contract test belong?

**ANALYSIS:** The test asserts FILE CONTENT shapes (frontmatter + body), not path resolution. R1 DeepSeek says test_paths.py because "project-root detection fixtures belong with path utilities." But test_paths.py is for `make_source_ref` (utils/paths.py), not for fixture validation. test_models.py is for frontmatter helpers — closer in shape since the assertions verify frontmatter formats. **However**: the test's primary purpose is fixture-contract verification, not a production-code test. There's no `test_conftest.py`. Folding into either is suboptimal but acceptable.

**DECISION:** **Fold into `test_paths.py`** as a `TestTmpProjectFixtureContract` class. Rationale: test_paths.py already has `tmp_path`-based fixture tests; the wiki-canonical-files contract is structurally similar to source-ref-path testing. Confidence: MEDIUM (acceptable trade-off; revisit if a `test_conftest.py` is created later).

### Q4 — AC6 canonical home (test_utils.py vs new test_utils_pages.py)

**Question:** R1 DeepSeek suggested creating new `test_utils_pages.py` if `kb.utils.pages` is substantial. **R1's premise is wrong:** the GOAL of the cycle is to REDUCE file count. Creating a new test file violates the freeze-and-fold rule.

**DECISION:** **Fold into existing `test_utils.py`.** test_utils.py already imports `from kb.utils.pages import normalize_sources` and tests utility helpers. Adding `page_id` / `scan_wiki_pages` tests preserves theme. Confidence: HIGH.

### Q5 — AC7 reload-leak isolation strategy

**Question:** `test_cycle12_config_project_root.py` uses `importlib.reload(kb.config)` 5 times across 5 tests. Folding into `test_paths.py` (which doesn't currently reload config) risks polluting sibling tests via cycle-19 L2 / cycle-20 L1 reload-leak.

**ANALYSIS:** Two strategies: (a) wrap moved tests in a class with a teardown that reloads config back to defaults; (b) accept the leak (matches current isolated-file behavior). Since the existing 5 tests in `test_cycle12_config_project_root.py` already exhibit this pattern WITHOUT cleanup, the current behavior must already be ordering-tolerant — pytest's import order seems to handle it. Adding a defensive teardown is cheap insurance.

**DECISION:** **Wrap the 5 moved tests in a `TestProjectRootResolution` class with an autouse fixture that reloads `kb.config` after each test** to restore the canonical PROJECT_ROOT/RAW_DIR/WIKI_DIR snapshot. This protects against future test additions to `test_paths.py` that rely on those globals. Confidence: HIGH.

### Q6 — Vacuous-test handling per C40-L3 + C41-L1

Per C40-L3, vacuous tests fold AS-IS + file BACKLOG.md upgrade-candidate entry. Identified vacuous tests:

- **AC8 / test_cycle12_frontmatter_cache.py:180-186** — `test_graph_builder_documents_case_sensitivity_caveat` asserts `gb.__doc__` contains "case-sensitiv" / "path" / "id". Pure docstring-introspection. **BACKLOG entry required.**
- **AC9 / test_cycle12_io_sweep.py:91-102** — `test_load_page_frontmatter_docstring_documents_mtime_caveat` asserts `load_page_frontmatter.__doc__` contains "mtime" / "filesystem" / FAT32 / SMB / OneDrive. **BACKLOG entry required.**
- **AC9 / test_cycle12_io_sweep.py:105-116** — `test_cycle12_io_doc_caveats_are_present` asserts `file_lock.__doc__`, `atomic_json_write.__doc__`, `atomic_text_write.__doc__` contain specific strings. **BACKLOG entry required.**

C41-L1 docstring-vs-code sanity check: I am NOT auto-upgrading these tests in cycle 43 (the user wants AS-IS folds + BACKLOG per C40-L3). Future upgrade cycle must run docstring-vs-code sanity per C41-L1 before replacing them.

### Q7 — AC11/AC12 host-shape preservation (class vs bare-function)

**Question:** Source files `test_cycle13_augment_raw_dir.py` and `test_cycle13_sweep_wiring.py` are class-shaped. Canonical homes `test_lint.py` and `test_cli.py` are bare-function-shaped per Codex R2.

**ANALYSIS:** cycle-40 L5 host-shape rule: prefer the host's predominant shape, but allow cohesive class additions when a single AC's tests share state (fixtures, helpers, parametrisation). Both AC11 and AC12 sources have 3-5 tightly-cohesive tests sharing helpers and fixtures.

**DECISION:** **Preserve class structure.** Fold `TestRawDirDerivation` (5 tests) into `test_lint.py` and `TestCliBootSweep` (3 tests) into `test_cli.py` as classes. Rationale: the cohesion is real, and class wrappers limit blast radius if a future maintainer rewrites surrounding bare-function tests. Confidence: HIGH.

### Q8 — Step-9 ordering (pivotal-first vs strict-AC-numbered)

**Question:** Should higher-risk folds run first (pivotal-first) or in AC order?

**ANALYSIS:** Codex R2 recommended pivotal-first: AC7 → AC1 → AC12 → AC9/AC8/AC6 → AC2/AC5/AC3/AC4 → AC11. Pivotal-first surfaces problems before low-risk folds become wasted work. But strict AC-numbered ordering is simpler to track and matches `feedback_batch_by_file` per-file commit grouping.

**DECISION:** **Strict AC-numbered ordering with one early dependency exception.** Run AC1 → AC12 in numeric order. Rationale: Each fold is independent; one fold's outcome doesn't affect another. Per-fold pytest verification surfaces problems immediately. Skip ordering complexity. Confidence: HIGH.

### Q9 — Test/file count drift verification per C26-L2 + C39-L3 + C41-L2

Pre-implementation baseline (captured 2026-04-27):
- **3014 tests collected** (`pytest --collect-only | tail -1`)
- **253 files** in tests/*.py (note: testing.md says 251 — pre-existing 2-file drift; cycle-42 hasn't bumped it; cycle-43 doc update will reconcile to actual count post-folds)

Post-cycle expectation (11 folds, no test count change):
- 3014 tests (test count preserved by fold semantics)
- 253 - 11 = 242 files

Doc sites to update at Step 12 per C26-L2 + C39-L3 + C41-L2 (load-bearing keyword grep):
- CLAUDE.md (Quick Reference)
- docs/reference/testing.md
- docs/reference/implementation-status.md
- README.md (tree block + Phase X stats)
- CHANGELOG.md (compact)
- CHANGELOG-history.md (per-cycle detail)
- BACKLOG.md (Phase 4.5 HIGH #4 progress note)

### Q10 — Cycle-42 working tree interference

The cycle-42 parallel session has been switching branches and committing during my Step 1-5 work, polluting my working tree. My Step 1-2 docs were accidentally committed to `cycle-42-phase46-dedup` (SHA 64b94b5) before being cherry-picked to `cycle-43-test-folds` (SHA 5ca6ca7).

**DECISION:** Continue in the shared working tree (worktree migration overhead exceeds remaining cycle's risk surface). Mitigations:
1. Verify branch BEFORE every commit (`git branch --show-current` must equal `cycle-43-test-folds`).
2. Skip files cycle-42 modifies in any commit set.
3. Commit each AC immediately after pytest passes — minimize working-tree exposure window.
4. **Skill-patch candidate (Step 16):** add a "shared-working-tree parallel-session hazard" rule to skill referencing this incident.

## CONDITIONS (must hold for Step 9 to proceed)

- **C1** — AC10 deferred via BACKLOG entry; cycle 43 fold count = 11 (not 12)
- **C2** — AC4 → test_paths.py (decided over test_models.py)
- **C3** — AC6 → test_utils.py (existing file, NOT new test_utils_pages.py)
- **C4** — AC7 wrapped in `TestProjectRootResolution` class with autouse config-reload teardown
- **C5** — AC8 + AC9 contain 3 vacuous docstring-introspection tests; fold AS-IS + 3 BACKLOG entries (per C40-L3, do NOT auto-upgrade)
- **C6** — AC11 + AC12 preserve source class structure into bare-function hosts (cohesion justifies class addition per C40-L5)
- **C7** — Per-AC commit messages follow `test(cycle 43 ACN): fold test_<source> into <canonical>`
- **C8** — Verify `git branch --show-current` returns `cycle-43-test-folds` BEFORE every commit (cycle-42 parallel-session hazard)
- **C9** — Step 12 doc update grep ALL of: CLAUDE.md, docs/reference/testing.md, docs/reference/implementation-status.md, README.md (per C26-L2 + C39-L3 + C41-L2)
- **C10** — Per C40-L3, every BACKLOG entry for a vacuous-test fold names the test, the source line, and the upgrade approach (e.g. "extract production-code helper, then test the helper")

## FINAL DECIDED SCOPE

**11 folds + 4 BACKLOG entries (3 vacuous-test upgrade candidates + 1 deferral note for AC10):**

| AC | Source | Canonical | Action |
|----|--------|-----------|--------|
| AC1 | test_cycle10_browse.py (1 test) | test_mcp_browse_health.py | FOLD |
| AC2 | test_cycle10_extraction_validation.py (4 tests) | test_ingest.py | FOLD |
| AC3 | test_cycle10_vector_min_sim.py (2 tests) | test_query.py | FOLD |
| AC4 | test_cycle11_conftest_fixture.py (1 test) | test_paths.py | FOLD as class |
| AC5 | test_cycle11_ingest_coerce.py (11 tests) | test_ingest.py | FOLD |
| AC6 | test_cycle11_utils_pages.py (8 tests) | test_utils.py | FOLD |
| AC7 | test_cycle12_config_project_root.py (5 tests) | test_paths.py | FOLD as class with reload-teardown |
| AC8 | test_cycle12_frontmatter_cache.py (7 tests) | test_models.py | FOLD + 1 BACKLOG entry (line 180 docstring test) |
| AC9 | test_cycle12_io_sweep.py (7 tests) | test_utils_io.py | FOLD + 2 BACKLOG entries (lines 91, 105) |
| AC10 | test_cycle12_sanitize_context.py | DEFER to cycle 44 | NO FOLD; 1 BACKLOG entry |
| AC11 | test_cycle13_augment_raw_dir.py (5 tests) | test_lint.py | FOLD as class |
| AC12 | test_cycle13_sweep_wiring.py (3 tests) | test_cli.py | FOLD as class |

**Total movements:** 54 tests across 11 commits + 4 BACKLOG entries = 58 net items per `feedback_batch_by_file`.

## ESCALATIONS

None. All questions resolved at this gate.
