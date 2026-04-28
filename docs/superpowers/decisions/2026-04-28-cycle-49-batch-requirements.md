# Cycle 49 — Batch requirements (test-fold continuation + dep-CVE re-confirm + tag bumps)

**Date:** 2026-04-28
**Branch:** `cycle-49-batch`
**Worktree:** `D:/Projects/llm-wiki-flywheel-c49` (created via `git worktree add` per C42-L4)
**Author:** primary-session per C37-L5 (≤15 ACs, ≤0 src files, primary holds full context post cycle-48)
**Cadence reference:** cycle 47 (3 folds), cycle 48 (2 folds), cycle 49 (4 folds proposed)

---

## Problem

Continuation of the hygiene cadence established in cycles 46-48:

1. **Phase 4.5 HIGH #4 freeze-and-fold rule** — ~190+ versioned `tests/test_cycle*.py` / `test_v0*.py` files still need folding into their canonical home files. Cycle 48 closed at 241 root-level test files; we want to keep chipping away with low-risk small files (24-50 LOC each).
2. **Dep-CVE re-confirmation** — The mechanical four-pip-audit + two-Dependabot-drift entries need timestamp refreshes from `2026-04-28 (cycle-48)` to `2026-04-28 (cycle-49)`. The cycle 48 BACKLOG also has three `cycle-49+` deferred items whose timestamps are already correct but whose narrative still references "cycle-48 re-confirmed N/A" — those need re-verification + tag bumps to `cycle-50+`.
3. **Doc count drift** — Cycle 48 closed at 241 files / 3025 tests across 3 narrative sites (CLAUDE.md, docs/reference/testing.md, docs/reference/implementation-status.md, README.md per C26-L2 + C39-L3). Cycle 49 will adjust to 237 / 3025 if 4 folds land cleanly.

## Non-goals

- **No `src/kb/` changes.** This is a pure tests/ + BACKLOG.md + docs/ cycle. No production-code edits, no API changes, no behavioural changes.
- **No new dependencies** added or bumped in `requirements.txt` / `pyproject.toml`. Step 11 PR-CVE diff must equal the empty set.
- **No CI matrix expansion.** Windows-latest re-enable is `cycle-49+` deferred; this cycle keeps the deferral and bumps the tag.
- **No fold of medium-size files (>60 LOC).** Larger folds need their own design pass; cycle 49 sticks to small mechanical folds.
- **No fold of cycle-44 M1/M2 lint-split-affected tests** (e.g. `test_cycle9_lint_checks.py` 42 LOC) — adjacent post-split surface is still settling per cycle-46 closeout; defer.
- **No new BACKLOG items added.** Surfacing new issues is allowed but goes into a Step 16 follow-up note, not the cycle's deliverable.
- **No `kb.mcp` / `kb.lint` augment shim deletions** beyond what's already in cycle 46. Compat shims stay.

## Acceptance Criteria

### Group A — Freeze-and-fold continuation (Phase 4.5 HIGH #4)

**AC1.** Fold `tests/test_cycle12_mcp_console_script.py` (24 LOC, 3 bare tests — `test_kb_mcp_package_exposes_main`, `test_kb_mcp_server_reexports_main_and_mcp`, `test_pyproject_has_kb_mcp_script_entry`) into `tests/test_v070.py` as a new `TestKbMcpConsoleScript` class with three `@staticmethod`-style methods. Source file deleted in the same commit. Each test must continue to pass (revert-verify: temporarily move the methods back to bare functions in the receiver and confirm pytest still collects + passes them).

**AC2.** Fold `tests/test_cycle9_capture_runtime_guard.py` (33 LOC, 1 bare test — `test_extract_items_via_llm_rejects_oversize_prompt`) into `tests/test_capture.py` as a top-level bare function (cycle-40 L5: a single isolated test does NOT need a class wrapper; preserve host-file shape — `tests/test_capture.py` already mixes class-based and bare-function tests). Source file deleted in the same commit.

**AC3.** Fold `tests/test_cycle9_package_exports.py` (36 LOC, 1 bare test — `test_ingest_source_export_lazy_loads_pipeline`, a `subprocess.run` PYTHONPATH probe) into `tests/test_v070.py` as a new `TestPackageExportLazyLoading` class. Source file deleted in the same commit. The receiver class boundary keeps the cycle-9 PEP-562 lazy-shim contract test grouped with related v070-era package-surface tests.

**AC4.** Fold `tests/test_cycle9_mcp_app.py` (37 LOC, 1 bare test — `test_instructions_tool_names_sorted_within_groups`, plus a private `_instruction_tool_groups` helper) into `tests/test_v070.py` as a new `TestMcpAppInstructions` class with `@staticmethod _instruction_tool_groups` per cycle-47 L1 (`@staticmethod` for module-internal helpers when no module-level helper home exists in receiver). Source file deleted in the same commit.

**AC5.** Each AC1-AC4 fold MUST be revert-verified per C40-L3: after the fold lands, I (the primary session) temporarily comment out the moved method body in the receiver, run pytest with `-x` to confirm the fold-receiver test fails (proving the test exercises real code paths), then restore. This is recorded in the per-task commit message footer (`Revert-verified: yes — moved-method body comment-out triggered pytest failure on …`). Revert verification is per-fold, not per-test (single representative test per fold is sufficient when fold has multiple tests).

**AC6.** File count: `find tests -maxdepth 1 -name '*.py' | wc -l` returns 237 after all four folds. Test count: `pytest --collect-only | tail -1` returns "3025 tests collected" (preserved). Both numbers verified at Step 10 CI hard gate AND re-verified at Step 12 doc update (per cycle-15 L4).

### Group B — Dep-CVE re-confirmation (mechanical timestamp refresh)

**AC7.** Re-confirm `lint/fetcher.py` `diskcache==5.6.3` CVE-2025-69872 entry. Update timestamp from `cycle-48 re-confirmed 2026-04-28` to `cycle-49 re-confirmed 2026-04-28`. Verify via `pip-audit --format=json` baseline that `fix_versions=[]` is unchanged AND `pip index versions diskcache` reports `5.6.3` is LATEST INSTALLED. Baseline saved to `.data/cycle-49/cve-baseline.json`.

**AC8.** Re-confirm `requirements.txt` `ragas==0.4.3` CVE-2026-6587 entry. Update timestamp `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28`. Verify `fix_versions=[]` unchanged AND `pip index versions ragas` reports `0.4.3` is LATEST INSTALLED. `grep -rnE "ragas|Ragas" src/kb` returns zero hits (runtime-import-free; dev-eval-only confirmed).

**AC9.** Re-confirm `requirements.txt` `litellm==1.83.0` GHSA trio (xqmj-j6mv-4862 + r75f-5x8p-qvmc + v4p8-mg3p-g94g). Update timestamp `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28`. Verify `pip download --no-deps litellm==1.83.14` wheel METADATA still pins `Requires-Dist: click==8.1.8` (transitive blocker preserved per cycle-22 L4). Wheel preserved at `.data/cycle-49/litellm-1.83.14-py3-none-any.whl` (or skip preserve if the cycle-48 wheel still satisfies the verification).

**AC10.** Re-confirm `.venv pip==26.0.1` CVE-2026-3219 entry. Update timestamp `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28`. Verify `pip index versions pip` reports `26.1` is LATEST AND advisory `first_patched_version` is still `null` per pip-audit baseline (cycle-22 L4 conservative posture: do NOT bump the pip installer until upstream confirms a patch). The cycle-47 wording correction (pip is `.venv` installer NOT `requirements.txt` pin per `grep -nE "^pip==" requirements.txt`) is preserved verbatim.

**AC11.** Re-confirm `Dependabot pip-audit drift on litellm GHSA-r75f-5x8p-qvmc` entry. Update narrative `cycle-37/38/.../48 re-confirmed drift persists 2026-04-28` to `… cycle-49 re-confirmed …`. Verify `gh api "repos/<owner>/<repo>/dependabot/alerts"` still emits alert ID #14. Baseline saved to `.data/cycle-49/alerts-baseline.json`.

**AC12.** Re-confirm `Dependabot pip-audit drift on litellm GHSA-v4p8-mg3p-g94g` entry. Same shape as AC11. Verify alert ID #15 still open in the Dependabot snapshot.

**AC13.** Re-confirm `requirements.txt` resolver-conflict entry (cycle-34 AC52 follow-up: arxiv 2.4.1 / crawl4ai 0.8.6 / instructor 1.15.1 transitive constraints). Update timestamp `cycle-48 re-confirmed 2026-04-28` → `cycle-49 re-confirmed 2026-04-28`. Verify all three conflicts persist verbatim per `pip check` output.

### Group C — Cycle tag bumps (forward-deferral)

**AC14.** Bump `cycle-49+` → `cycle-50+` on three N/A prerequisite-missing entries — windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn investigation, TestWriteItemFiles POSIX off-by-one — in `BACKLOG.md` lines 164-168. Update each "Cycle-48 re-confirmed N/A" narrative to "Cycle-49 re-confirmed N/A — prerequisite missing: <prereq>; tag bumped to cycle-50+." None of the three prerequisites became available during cycle 49 (no self-hosted Windows runner; no POSIX shell; no GHA-Windows reproducer).

**AC15.** Bump `cycle-47+` → `cycle-49+` on the two Dependabot drift entries (litellm GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g) at BACKLOG lines 170/172, mirroring the cycle-46 → cycle-47 → cycle-49 pattern (skipped cycle-48 per cycle-46 precedent — drift entries roll forward together with their parent advisory).

### Group D — BACKLOG hygiene (Phase 4.5 HIGH #4 progress note)

**AC16.** Append cycle-49 progress to the Phase 4.5 HIGH #4 progress note at BACKLOG.md line 91. New text appended at the end of the existing parenthetical: *"Cycle 49 continued cadence with 4 small folds: `test_cycle12_mcp_console_script.py` (24 LOC, 3 tests) → `tests/test_v070.py`, `test_cycle9_capture_runtime_guard.py` (33 LOC, 1 test) → `tests/test_capture.py`, `test_cycle9_package_exports.py` (36 LOC, 1 test) → `tests/test_v070.py`, `test_cycle9_mcp_app.py` (37 LOC, 1 test) → `tests/test_v070.py`; file count 241 → 237 (-4); test count preserved at 3025."* HIGH item remains open (~186+ versioned files still to fold post cycle-49).

### Group E — Doc sync

**AC17.** Update file-count + test-count narratives across all C26-L2 + C39-L3 sites (CLAUDE.md Quick Reference, README.md, docs/reference/testing.md, docs/reference/implementation-status.md) to "3025 tests / 237 files (3014 passed + 11 skipped on Windows local)" per the cycle 48 → 49 delta. Grep verification: `grep -rn "241 files\|3025 tests / 241" CLAUDE.md README.md docs/reference/` should return zero matches after the update.

**AC18.** Add cycle 49 entry to `CHANGELOG.md` `[Unreleased]` Quick Reference (newest first, compact Items / Tests / Scope / Detail format) AND full bullet-level detail to `CHANGELOG-history.md` (newest first). Commit-count claim uses `+TBD` per C30-L1 self-referential pattern, backfilled to actual on the squash-merge landing commit.

---

## Blast radius

- **Modified files (expected):**
  - `tests/test_v070.py` — receives 3 new test classes (`TestKbMcpConsoleScript`, `TestPackageExportLazyLoading`, `TestMcpAppInstructions`)
  - `tests/test_capture.py` — receives 1 new bare function (`test_extract_items_via_llm_rejects_oversize_prompt`)
  - `tests/test_cycle12_mcp_console_script.py` — DELETED
  - `tests/test_cycle9_capture_runtime_guard.py` — DELETED
  - `tests/test_cycle9_package_exports.py` — DELETED
  - `tests/test_cycle9_mcp_app.py` — DELETED
  - `BACKLOG.md` — 7 dep-CVE timestamp refreshes (AC7-AC13) + 3 cycle tag bumps (AC14) + 2 Dependabot drift bumps (AC15) + Phase 4.5 HIGH #4 progress note (AC16)
  - `CLAUDE.md` — Quick Reference test/file count (AC17)
  - `README.md` — test/file count narrative (AC17)
  - `docs/reference/testing.md` — test/file count narrative (AC17)
  - `docs/reference/implementation-status.md` — test/file count narrative (AC17)
  - `CHANGELOG.md` — `[Unreleased]` Quick Reference (AC18)
  - `CHANGELOG-history.md` — full per-cycle archive (AC18)
- **Untouched:** `src/kb/` (zero changes); `requirements.txt` / `pyproject.toml` (zero pin changes); `.github/workflows/` (zero CI changes).
- **CVE PR-introduced diff (Step 11):** expected empty set — no dependency changes.

## Constraints / pre-conditions

1. **C42-L4 worktree discipline** — All work happens in `D:/Projects/llm-wiki-flywheel-c49`. Verify branch on every commit via `git branch --show-current` (expected: `cycle-49-batch`). Never edit files in the main worktree (`D:/Projects/llm-wiki-flywheel`) during cycle 49. Editable install was last repointed to cycle-48 worktree post cycle-48 cleanup; before AC1 starts, repoint via `pip install -e .` from `D:/Projects/llm-wiki-flywheel-c49`.
2. **C40-L4 path-portability** — All cycle-49 artifacts (`.data/cycle-49/`) MUST use project-relative paths, NOT bash `/tmp/` paths. The `.data/cycle-49/` directory is gitignored.
3. **C41-L1 docstring-vs-code sanity** — Each fold's pre-existing test docstring/comment is preserved verbatim in the receiver. If a fold reveals an out-of-date docstring (cycle 48 surfaced this on `save_page_frontmatter`), file as a Step 16 follow-up, do NOT silently fix it.
4. **C40-L5 host-shape preservation** — Bare-function tests fold as bare functions if the receiver is bare-function-shaped; class-shaped if the receiver is class-shaped; new class introduced for fold cohesion when receiver mixes both (acceptable per cycle-43 L4).
5. **Cycle-23 L1 docstring/import discipline** — Method definitions inside fold-receiver classes must NOT introduce function-local imports before the closing `"""` of the docstring (orphans `__doc__`).
