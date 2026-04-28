# Cycle 47 — Batch Requirements

**Date:** 2026-04-28
**Branch:** cycle-47-batch
**Worktree:** `D:\Projects\llm-wiki-flywheel-c47`
**Pattern:** Backlog hygiene + freeze-and-fold continuation + dep-CVE re-verification + cycle-47+ spawn-entry triage

## Problem

The Phase 4.5 HIGH #4 freeze-and-fold migration has ~190+ versioned test files
remaining after cycle 46. The cycle-46 self-review explicitly "prioritised
Phase 4.6 LOW shim deletion (no new fold this cycle)" — cycle 47 resumes the
fold cadence with a small targeted batch.

Five BACKLOG entries are explicitly tagged `(cycle-47+)`:

1. `tests/` windows-latest CI matrix re-enable — investigate threading-related
   test that hangs at `threading.py:355` after cycle-23 multiprocessing test
   was skipif'd; apply targeted skipif marker OR file refined fix-shape.
2. `tests/` GHA-Windows multiprocessing spawn investigation — requires
   self-hosted Windows runner; no progress possible without that prerequisite.
3. `tests/test_capture.py::TestWriteItemFiles` POSIX off-by-one — requires
   POSIX shell access for direct instrumentation; defer further unless
   sandbox dispatch fits.
4. Dependabot pip-audit drift on litellm GHSA-r75f-5x8p-qvmc — re-confirm
   drift persists; refresh BACKLOG timestamp.
5. Dependabot pip-audit drift on litellm GHSA-v4p8-mg3p-g94g — same shape.

Five Phase 4.5 MEDIUM dep-CVE entries (diskcache, ragas, litellm-1.83.x,
pip-26.0.1) need cycle-47 re-verification stamps to keep "no upstream fix"
posture honest (cycle-22 L4: advisories can shift between cycles).

## Non-goals

- **No new feature work.** This is a hygiene + verify cycle.
- **No deep architectural refactors.** Phase 4.5 HIGH items (compile/compiler.py
  rename, mcp/ async refactor, ingest/pipeline.py state-store fan-out) all
  require dedicated cycles with full design eval. Batch hygiene cycles MUST
  not lard scope.
- **No real GHA-Windows debugging.** I do not have a Windows GHA runner. I can
  read code, identify likely-hanging tests, and apply skipif markers, but I
  cannot reproduce the hang. If best-effort identification fails, refine the
  BACKLOG entry with the search frontier as cycle-47 progress.
- **No POSIX-shell investigation.** Same prerequisite gap as above; refine
  the entry instead of best-guess fixes.
- **No production-code refactors that could destabilise Phase 5 readiness.**
  Folds are test-side only; if a fold reveals a production gap, file BACKLOG
  upgrade-candidate (per C40-L3) and SKIP the fold.
- **No Phase 5 work.** Per user instruction "before Phase 5 items".

## Acceptance Criteria

### Group A — dep-CVE re-verification (mechanical, ~6 ACs)

- **AC1** — `requirements.txt` `diskcache==5.6.3`. Re-run `pip index versions
  diskcache` + `pip-audit --format=json`. Confirm: (a) 5.6.3 = LATEST, (b)
  pip-audit `fix_versions` empty for GHSA-w8v5-vhqr-4h9v. Update BACKLOG
  entry timestamp from 2026-04-28 (cycle-46) to 2026-04-28 (cycle-47, same
  date but explicit cycle stamp in parenthesised text).
- **AC2** — `requirements.txt` `ragas==0.4.3`. Re-verify CVE-2026-6587 still
  has empty `fix_versions`; 0.4.3 still LATEST per `pip index versions ragas`.
  Refresh BACKLOG timestamp.
- **AC3** — `requirements.txt` `litellm==1.83.0` (advisories
  GHSA-xqmj-j6mv-4862, GHSA-r75f-5x8p-qvmc, GHSA-v4p8-mg3p-g94g). Re-verify
  the LATEST `pip index versions litellm` output still pins
  `Requires-Dist: click==8.1.8` via wheel-METADATA inspection (`pip download
  --no-deps litellm==<latest>` + `zipfile.ZipFile` METADATA extraction).
  Refresh BACKLOG timestamp.
- **AC4** — `requirements.txt` `pip==26.0.1` (CVE-2026-3219). Re-verify pip
  26.1 LATEST per `pip index versions pip`; advisory metadata via
  `gh api /advisories/GHSA-58qw-9mgm-455v --jq '{patched_versions, vulnerable_version_range}'`
  still null-patched (cycle-22 L4 conservative posture: do NOT bump).
  Refresh BACKLOG timestamp.
- **AC5** — Dependabot `litellm GHSA-r75f-5x8p-qvmc` drift. Re-confirm:
  (a) `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` still lists
  this GHSA as open, (b) `pip-audit --format=json` on live venv does NOT
  emit this ID. Refresh BACKLOG timestamp; do not add to `--ignore-vuln`
  unless pip-audit catches up.
- **AC6** — Dependabot `litellm GHSA-v4p8-mg3p-g94g` drift. Same shape as
  AC5; refresh BACKLOG timestamp.

### Group B — Test-fold continuation (Phase 4.5 HIGH #4, ~3-5 ACs)

- **AC7** — Pick 3-5 small versioned test files (≤200 LOC each, behavior
  contained in canonical module file) for fold. Candidate set (final
  selection at Step 5 design gate):
  - `test_cycle11_task6_mcp_ingest_type.py` → `test_mcp_core.py` or
    `test_mcp_ingest.py` after grep-verify
  - `test_cycle13_frontmatter_migration.py` → `test_models.py` or
    `test_ingest.py`
  - `test_cycle14_augment_key_order.py` → `test_lint_augment_split.py`
    (cycle-44 + cycle-46 destination)
  - `test_cycle14_save_frontmatter.py` → `test_models.py`
  - `test_cycle16_config_constants.py` → `test_config.py` if exists,
    else `test_models.py`
  - `test_cycle19_lint_redundant_patches.py` → canonical lint test file
- **AC8** — For each folded file: read source, identify behavior-equivalent
  classes/parametrize cases, paste into canonical with cycle-stamped section
  comment, delete the versioned file, run isolation + cross-test (cycle-43
  L1: pre-fold + post-fold pytest must show identical pass count for the
  affected test IDs).
- **AC9** — For any vacuous-test, signature-only-test, or
  `inspect.getsource`-style test discovered during fold: do NOT fold; file
  C40-L3 BACKLOG.md upgrade candidate with concrete behavior-test shape and
  delete the cycle-N file (or KEEP it pending upgrade — design gate decides
  at Step 5).
- **AC10** — Net test count delta computed: `pytest --collect-only | tail -1`
  before fold vs after. Should remain ≈3025 (folded tests preserved as
  parametrize cases or class methods, not deleted).

### Group C — Windows CI matrix investigation (cycle-47+ spawn entry, ~2 ACs)

- **AC11** — Best-effort identification of the test hanging at
  `threading.py:355` on GHA windows-latest. Read all tests using
  `threading.Thread`, `concurrent.futures.ThreadPoolExecutor`,
  `multiprocessing` in cycle 23-27 era files. Identify candidate(s) most
  likely to deadlock under GHA Windows (limited resources, slow shutdown).
  If a single test or test file is high-confidence: apply `skipif(os.environ.get("CI") == "true")`
  with cycle-47 marker. Otherwise: refine BACKLOG entry with frontier list
  (specific test IDs to instrument first) for cycle-48+.
- **AC12** — Re-enable matrix `[ubuntu-latest, windows-latest]` only if AC11
  applied a high-confidence skipif AND the cycle-23 spawn-bootstrap test was
  also reverified as skipif'd. Otherwise: explicit "DEFER to cycle-48+"
  decision documented in BACKLOG with the AC11 frontier list.

### Group D — BACKLOG hygiene (~3 ACs)

- **AC13** — Update Phase 4.5 HIGH #4 progress note with cycle-47 status:
  net file count delta, which versioned files folded, cumulative remaining
  estimate.
- **AC14** — Refresh ALL `(cycle-47+)` tagged entries with cycle-47
  re-confirmation timestamps. Tag should NOT escalate to cycle-48+ unless
  the entry is actively closed; spawn entries that remain open keep
  `(cycle-47+)` AND add `(cycle-47 re-confirmed N/A — prerequisite missing: <reason>)`.
- **AC15** — Refresh dep-CVE re-verification dates in all 4 dep entries +
  2 Dependabot drift entries (per AC1-AC6).

### Group E — Documentation (~5 ACs)

- **AC16** — `CHANGELOG.md` cycle-47 Quick Reference entry under
  `[Unreleased]`. Compact format: Items / Tests / Scope / Detail.
- **AC17** — `CHANGELOG-history.md` full per-cycle bullet detail (newest
  first), enumerating every AC closed.
- **AC18** — `CLAUDE.md` Quick Reference: refresh test count (3025 → actual
  post-fold), update last-cycle stamp.
- **AC19** — `README.md` tree-block test count if drifted (per C39-L3:
  README is a count-narrative site).
- **AC20** — `docs/reference/testing.md` cycle 47 history entry +
  `docs/reference/implementation-status.md` cycle 47 latest-cycle notes
  (per C26-L2 + cycle-35 extension).

## Blast radius

| Surface | Effect | Risk |
|---|---|---|
| `BACKLOG.md` | Timestamp refreshes + HIGH #4 progress note + cycle-47+ entries | LOW — text-only, no code path change |
| `tests/test_cycle*.py` (5-8 files) | Files DELETED, content preserved in canonical files as parametrize/class methods | MEDIUM — fold-time test count delta MUST equal zero per AC10; cross-fold ordering can surface hidden test fixture interactions (cycle-22 L3 reload-leak class) |
| `tests/test_*.py` (canonical receivers, 3-5 files) | Class additions + parametrize case additions | LOW — additive only, no existing test code modified |
| `requirements.txt` | NO CHANGES if AC1-AC6 confirm all "no upstream fix" | LOW — verification only; if CVE state changed, defer fix to next cycle to keep batch scope hygiene-only |
| `.github/workflows/ci.yml` | Either skipif-marker addition (AC11) OR matrix re-enable (AC12) — only ONE may land per cycle-36 L1 | MEDIUM — touches CI config; revertable via single commit |
| `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`, `README.md`, `docs/reference/*.md` | Documentation sync per Step 12 routing rule | LOW — text-only |
| `src/kb/**` | NO CHANGES expected; if a fold surfaces a missing production helper, file BACKLOG and skip the fold (AC9) | LOW — guarded by AC9 |

## Dependencies

- BACKLOG dep-CVE entries (lines 126-136 + 170-172 in `BACKLOG.md` on `main`
  at commit `47fbf4e`).
- Phase 4.5 HIGH #4 progress note (line 91 in `BACKLOG.md`).
- Recent CHANGELOG entries (cycles 38-46) for fold-pattern reference.
- C26-L2 + C39-L3 + cycle-15 L4 + C42-L4: count re-verification + parallel
  cycle branch discipline (the user explicitly noted "other cycles may run
  in parallel").

## Constraints

- **Worktree isolation enforced** via `D:\Projects\llm-wiki-flywheel-c47`
  on `cycle-47-batch` branch (per cycle-43 L1 + cycle-42 L4).
- **Branch discipline at every commit:** `git branch --show-current` =
  `cycle-47-batch` for every Edit-Write-commit cycle (cycle-42 L4).
- **Editable install repointed** to worktree (cycle-46 strategy:
  `pip install -e D:\Projects\llm-wiki-flywheel-c47` against shared
  `.venv`).
- **Step 11 PR-CVE diff** uses `.data/cycle-47/cve-baseline.json` (project
  relative path per cycle-22 L1 + cycle-40 L4 — never `/tmp` on Windows).
