# Cycle 52 — Backlog hygiene + freeze-and-fold continuation

**Date:** 2026-04-28
**Branch:** `cycle-52-batch` (worktree at `D:/Projects/llm-wiki-flywheel-c52`)
**Cycle type:** Hygiene-only — backlog freeze-and-fold + dep-CVE re-confirm.
**Previous cycle:** Cycle 51 (PR #74 merged 2026-04-28; 4 folds, 233 → 229 files).

## Problem

Per Phase 4.5 HIGH `tests/` coverage-visibility item, ~190+ versioned test files
(`test_v0NNN_taskNN.py` / `test_cycleNN_*.py` / `test_phase4_audit_*.py`) still
exist after cycle 51's 4-fold pass. Each file fragments per-module coverage
visibility — to verify a module has tier-budget / behaviour coverage, an
auditor must grep across many files because canonical `test_<module>.py`
files lack the cycle-tagged additions.

The freeze-and-fold rule (Phase 4.5 HIGH carry-over): once a version ships,
fold its tests INTO the canonical module file; renames where appropriate to
avoid clashes with existing test names.

## Non-goals

- Production code changes — fold operations only, no `src/kb/` edits this cycle
  (mirrors cycles 47..51 hygiene posture).
- New tests — preserve all 3025 tests verbatim across the fold.
- New CVE patches — re-confirm the four open Dependabot alerts and their
  no-upstream-fix profile; do NOT bump pins speculatively.
- New features — defer Phase 5 / Tier-1 items.
- C42-L4 footgun: parallel cycles may be running; isolate via worktree
  (`D:/Projects/llm-wiki-flywheel-c52`) and verify `git branch --show-current`
  returns `cycle-52-batch` before every commit.

## Acceptance Criteria

### Fold operations (4 candidates, ranked by file size ascending)

**AC1 — Fold `test_cycle19_prune_base_consistency_anchor.py` (2762 B / 2 tests) into `tests/test_compile.py`.**
- Test 1 (`test_prune_base_uses_canonical_rel_path_at_both_sites`) is a known-weak
  `inspect.getsource` test per C40-L3. Move as-is into the `# ── Compiler tests ─`
  section as a bare function; file BACKLOG.md upgrade candidate (cycle-53+) per
  C40-L3 — DO NOT attempt in-fold C41-L1 behavioral upgrade because the docstring
  rationale (cycle-19 design.md AC14 DROP: "A behavioural test would need to
  construct a divergence scenario the fix already prevents — i.e. would be
  vacuous") is load-bearing — both sites' divergence is exactly what the fix
  prevents, so any behavioural divergence-driver test is also vacuous.
- Test 2 (`test_manifest_key_for_alias_is_canonical_rel_path_at_module_scope`)
  is already a strong identity-equality test; move as-is.
- Receiver section: `# ── Compiler tests ─` after the existing `_canonical_rel_path`
  / `manifest_key_for` related tests.
- Revert-verify per C40-L3: insert `assert False` mid-function, run isolation
  pytest, confirm FAIL, restore.

**AC2 — Fold `test_cycle19_lint_redundant_patches.py` (2843 B / 1 test) into `tests/test_lint.py`.**
- AST-walk lint guard test (acceptable structural test — lints test files, not
  src/, so cycle-11 L1 inspect-source ban does not apply per C40-L3 carve-out for
  meta-tests). Move as-is into a new section `# ── Lint guards (cycle 52 fold) ─`
  at the bottom after `# ── Runner tests ─`.
- Helpers `_method_uses_tmp_kb_env` and `_method_body_text` move with the test.
- Receiver section: appended after existing `# ── augment._resolve_raw_dir branch coverage ─`
  block.
- Revert-verify per C40-L3.

**AC3 — Fold `test_cycle15_load_all_pages_fields.py` (2975 B / 6 tests) into `tests/test_utils.py`.**
- Strong behavioural tests, already use `tmp_path` + production `load_all_pages`.
- Receiver section: existing `# ── load_all_pages ─` block. Insert after the
  existing `test_load_all_pages_normalizes_sources` test.
- Helper `_write_page` clashes with no existing helper (test_utils.py has no
  function named `_write_page`); rename to `_write_concept_page` for clarity per
  cycle-50 Step-5 helper-name uniqueness rule.
- Revert-verify per C40-L3.

**AC4 — Fold `test_cycle15_query_tier1_wiring.py` (3082 B / 2 tests) into `tests/test_query.py`.**
- Behavioural monkeypatch-based tests; preserves cycle-14/15 wiring.
- Receiver section: new section `# ── Tier-1 budget wiring (cycle 52 fold) ─`
  inserted after the existing `# ── Query integration tests ─` block (line ~280).
- Helper `_summary_page` may clash; check tests/test_query.py for an existing
  same-named helper; rename to `_tier1_summary_page` if needed per Step-5
  helper-name uniqueness.
- Revert-verify per C40-L3.

### Hygiene gates

**AC5 — Each fold is its own commit; commit message body uses `confirmed`
NOT `verify` per C35-L4 + C50-L1.** Use `git commit -F .data/cycle-52/commit-fold-N.txt`
to bypass shell-escape pitfalls and keep `--no-verify` substring out of the
log per C50-L1.

**AC6 — Test count preserved at 3025 across all folds.** Verify with
`pytest --collect-only -q | tail -1` after each fold.

**AC7 — File count drops from 229 → 225 (-4).** Verify with
`find tests -maxdepth 1 -name '*.py' | wc -l`.

**AC8 — Each fold runs ISOLATION pytest per C51-L1 BEFORE commit.**
`pytest <receiver>::<new_target> -v` for every moved test/method, not just
full-file. Catches latent test-ordering bugs the moved test was riding (e.g.
cycle-19 L2 lazy-init dependencies on module attributes).

**AC9 — Worktree branch discipline per C42-L4.** Run `git branch --show-current`
before every Edit and commit; expected `cycle-52-batch`. System-reminder showing
PRE-EDIT content of recently-edited files = checkout-revert signal — cherry-pick
to correct branch + reset wrong branch.

### Doc + CVE gates

**AC10 — CHANGELOG.md + CHANGELOG-history.md + BACKLOG.md updated
per C26-L2 + C39-L3 + C41-L2.** All count narratives (`3025 tests`, `225 files`,
`-4` delta) consistent across CLAUDE.md, README.md, docs/reference/testing.md,
docs/reference/implementation-status.md.

**AC11 — Dep-CVE baseline (`.data/cycle-52/`) shows the same 4 open alerts as
cycle 51.** `pip-audit --format=json` no new CVE IDs introduced; `pip index versions <pkg>`
re-confirms no upstream patches landed for diskcache (5.6.3), ragas (0.4.3), pip
(26.0.1 installer), litellm (1.83.7+ fix blocked by click pin). BACKLOG.md
re-confirmed timestamp updated to 2026-04-28.

**AC12 — Worktree cleanup ordering per C51-L2.** After PR squash-merge: do NOT
pass `--delete-branch` to `gh pr merge`. Order: `gh pr merge --squash` →
main-worktree fetch+pull → `git worktree remove <path> --force` →
`git branch -D cycle-52-batch` → `git worktree list` confirm.

**AC13 — Edit-tool path-vs-content tracking per C51-L3.** At Step 12 entry,
batch-pre-Read every doc-target file in the worktree (`docs/reference/testing.md`,
`docs/reference/implementation-status.md`, `CLAUDE.md`, `README.md`,
`CHANGELOG.md`, `CHANGELOG-history.md`, `BACKLOG.md`) before the Edit pass to
avoid harness "you must Read first" errors.

## Blast radius

- `tests/` — 4 file deletions, 4 receiver-file additions (no new src/ edits).
- `BACKLOG.md` — Phase 4.5 HIGH `tests/` carry-over note updated; CVE timestamps
  refreshed; possible cycle-53+ upgrade candidate filed for cycle-19 prune-base
  inspect.getsource test (AC1).
- `CHANGELOG.md` + `CHANGELOG-history.md` — cycle-52 entry; one commit-tally
  rule per C30-L1 (use `+TBD`, backfill post-merge).
- `CLAUDE.md` — Quick Reference test-count + file-count update.
- `README.md` — tree-block test count.
- `docs/reference/testing.md` + `implementation-status.md` — count narratives.
- No `src/kb/` files modified.
