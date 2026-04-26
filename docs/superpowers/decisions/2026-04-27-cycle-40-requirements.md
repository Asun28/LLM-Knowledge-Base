# Cycle 40 — Backlog hygiene + freeze-and-fold continuation

**Date:** 2026-04-27
**Owner:** dev_ds skill (primary session, post cycle-39 amendment)
**Predecessor:** Cycle 39 (PR #53 + #54 + #55 — backlog hygiene + dep-drift re-verification + cycle-38 fold)

## Problem

`BACKLOG.md` Phase 4.5 HIGH item #4 (`tests/` coverage-visibility) flags ~208 versioned test files vs 71 canonical files, with the freeze-and-fold rule explicitly defined: *"once a version ships, fold its tests INTO the canonical module file (`test_v0917_dedup.py` → `test_query.py::class TestDedup`)."* Cycle 4 codified the rule; cycle 39 folded one cycle-38 file as proof-of-mechanic. Cycle 40 continues the fold for three cycle-10/11 files chosen for clean-cut module ownership and absence of autouse-fixture coupling.

The same cycle re-verifies all standing dep-CVE entries (4 alerts: 3 litellm + 1 ragas; plus 4 pip-audit IDs covering diskcache/ragas/litellm/pip) and the three resolver conflicts cycle 39 last touched 2026-04-26 — Dependabot snapshot taken 2026-04-27 09:30 GMT+12 confirms identical state (4 alerts, IDs 12-15). Re-verification entries get the `(cycle-40 re-confirmed 2026-04-27)` marker, matching the cycle-39 marker convention.

The two litellm Dependabot-drift entries (`GHSA-r75f-5x8p-qvmc`, `GHSA-v4p8-mg3p-g94g`) remain in the cycle-40+ deferral row because pip-audit on the live install env still does NOT emit these IDs as of 2026-04-27 (1-day rerun confirms). They get the same re-confirmation marker.

## Non-goals

- No `src/kb/` code changes (pure hygiene).
- No fold of cycle-12+ test files (each new fold adds one round of design-question resolution; keep cycle scope bounded).
- No CI matrix changes (windows-latest re-enable remains cycle-40+ deferral per cycle-36 L1 CI-cost discipline; not this batch).
- No POSIX off-by-one investigation (`test_capture.py::TestWriteItemFiles`) — needs POSIX shell, not tractable from Windows-only environment; remains cycle-40+ deferral.
- No GHA Windows multiprocessing spawn investigation — needs self-hosted Windows runner, not tractable; remains cycle-40+ deferral.
- No capture.py two-pass write architecture (Phase 5 pre-merge CRITICAL — explicitly excluded by user instruction "before Phase 5 items").
- No new tests added; only test FILE consolidation.

## Acceptance Criteria

### Group A — Test fold continuation (Phase 4.5 HIGH #4)

- **AC1** — Fold `tests/test_cycle10_safe_call.py` (5 tests, 75 LoC) into `tests/test_mcp_browse_health.py` as `class TestSanitizeErrorStrAtMCPBoundary`. All 5 tests exercise `_sanitize_error_str` (mcp.app), `_safe_call` (lint._safe_call), and the `kb_lint` MCP-boundary surface — natural home is the MCP browse/health canonical file. Source file deleted post-fold. Test count invariant: 5 tests preserved.

- **AC2** — Fold `tests/test_cycle10_linker.py` (2 tests, 13 LoC) by splitting per actual symbol ownership: test 1 (`test_detect_source_drift_docstring_documents_deletion_pruning_persistence`) targets `kb.compile.compiler.detect_source_drift` → fold to `tests/test_compile.py` as bare function; test 2 (`test_wikilink_display_escape_preserves_pipe_via_backslash`) targets `kb.utils.text.wikilink_display_escape` → fold to `tests/test_utils_text.py` as bare function. Source file deleted post-fold. Test count invariant: 2 tests preserved (1 + 1 across two targets).

- **AC3** — Fold `tests/test_cycle11_stale_results.py` (4 tests, 50 LoC) into `tests/test_query.py` as `class TestFlagStaleResultsEdgeCases`. All 4 tests exercise `kb.query.engine._flag_stale_results` — canonical home is `test_query.py`. Preserve cycle-15 AC1 reference comment in the migrated parametrize block. Source file deleted post-fold. Test count invariant: 4 tests preserved.

### Group B — Dep-CVE re-verification (cycle-39 carry-over)

- **AC4** — Re-verify diskcache `CVE-2025-69872` / `GHSA-w8v5-vhqr-4h9v` state. Run `pip index versions diskcache` + `pip-audit --format=json` on live env; confirm 5.6.3 = LATEST, `fix_versions` empty. Update BACKLOG entry with `(cycle-40 re-confirmed 2026-04-27)` marker.

- **AC5** — Re-verify ragas `CVE-2026-6587` / `GHSA-95ww-475f-pr4f` state. Run same probes; confirm 0.4.3 = LATEST, no upstream fix. Update BACKLOG marker.

- **AC6** — Re-verify litellm 1.83.0 advisories `GHSA-xqmj-j6mv-4862` + `GHSA-r75f-5x8p-qvmc` + `GHSA-v4p8-mg3p-g94g` state. Confirm `pip download litellm==1.83.14 --no-deps` METADATA still pins `Requires-Dist: click==8.1.8` (unchanged from cycle 39). Update BACKLOG marker.

- **AC7** — Re-verify pip 26.0.1 `CVE-2026-3219` / `GHSA-58qw-9mgm-455v` state. Run `pip index versions pip` + `pip-audit`; confirm 26.0.1 = LATEST, `fix_versions` empty. Update BACKLOG marker.

### Group C — Resolver + Dependabot drift re-verification (cycle-40+ deferral row)

- **AC8** — Re-verify three resolver conflicts: arxiv requires requests~=2.32.0 vs installed 2.33.0; crawl4ai requires lxml~=5.3 vs installed 6.1.0; instructor requires rich<15.0.0 vs installed 15.0.0. Run `pip check`; confirm all three conflicts persist verbatim. Update BACKLOG entry with cycle-40 marker.

- **AC9** — Re-verify Dependabot drift on litellm `GHSA-r75f-5x8p-qvmc` (critical). Confirm pip-audit on live env still does not emit this ID, and Dependabot still reports it open with `first_patched: 1.83.7`. Update BACKLOG marker.

- **AC10** — Re-verify Dependabot drift on litellm `GHSA-v4p8-mg3p-g94g` (high). Same probes; same confirmation; update BACKLOG marker.

### Group D — BACKLOG hygiene update

- **AC11** — Update Phase 4.5 HIGH #4 (`tests/` coverage-visibility) BACKLOG entry to record cycle-40 fold progress: cycle-38-fold (1 file in cycle 39) + 3 files in cycle 40 = 4 files total folded. Note the running deferred count (208 versioned files at cycle-39 end → 205 at cycle-40 end). The HIGH item itself is NOT closed (full fold of all 200+ files would require many more cycles); only the progress note advances.

## Blast radius

| Layer | Change |
|---|---|
| `src/kb/**` | NONE |
| `tests/**` | -3 source files; +3 canonical files modified (test_mcp_browse_health.py, test_compile.py, test_utils_text.py, test_query.py — note 4 canonical files because AC2 splits into 2) |
| Test count | 3014 → 3014 (invariant) |
| `BACKLOG.md` | 7 entries get cycle-40 markers + AC11 progress note |
| `CHANGELOG.md` + `-history.md` | Cycle 40 narrative under [Unreleased] |
| `CLAUDE.md` | Test-FILE count: 258 → 255 (3 files deleted); test count unchanged |
| `README.md` | Per C39-L3 — test-FILE count narrative if present |
| `docs/superpowers/decisions/` | 4 cycle-40 docs (requirements, threat-model, design, plan) + post-merge self-review |
| `.github/workflows/*.yml` | NONE |
| `requirements.txt` | NONE |

Reversibility: high. Test folds are pure relocations; if a fold breaks under full-suite ordering, revert the canonical file to pre-fold state and restore the source file from git history. Dep re-verifications are doc-only.

## Test plan (high-level)

1. Pre-fold baseline: `python -m pytest --collect-only -q` → expect "3014 tests collected".
2. Per-fold workflow (AC1-AC3): read source → read target → append class/function with preserved imports + bodies → delete source → re-run pytest --collect-only → assert count unchanged.
3. After all 3 folds: run full suite (`python -m pytest -q`) → assert 3003 passed + 11 skipped (or 3014 collected total).
4. Run `ruff check tests/` + `ruff format --check tests/` → all pass.
5. Dep re-verifications execute on live `.venv` install (fixed cycle-22 L1 footgun: drop `-r requirements.txt` from pip-audit, audit installed env).
