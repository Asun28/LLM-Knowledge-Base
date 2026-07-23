# Cycle 53 — Requirements

**Date:** 2026-04-29
**Type:** Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm
**Sequence:** Continues cycles 47..52 cadence (4 folds per cycle, file-count -4)
**Worktree:** `.claude/worktrees/cycle-53` on branch `worktree-cycle-53`

## Problem

Cycles 47..52 established a steady-state freeze-and-fold cadence: 4 small versioned-test
files folded into canonical receivers per cycle, file count 245 → 225, test count
preserved at 3025. ~190+ versioned files remain. The dep-CVE shape has been static
across 8 weekly re-confirms (diskcache / ragas / litellm / pip — all with no upstream
fix as of 2026-04-28). Cycle 53 continues this two-track work.

## Non-goals

- No production code changes (signature-preserving moves only — Step 10 simplify-pass
  skip-when applies).
- No M3 (mcp/core.py split) work — that landed in cycle 45 with deferred follow-ups.
- No GHA-Windows matrix re-enable (still tagged cycle-53+ pending self-hosted runner).
- No POSIX test_capture.py investigation (still tagged cycle-53+ pending POSIX shell).
- No litellm 1.83.7+ bump (still blocked by `click==8.1.8` transitive — cycle-52 verified).
- No new feature ACs from Phase 5 backlog.

## Acceptance Criteria

### AC1 — Pick 4 fold candidates within size envelope
Candidates picked from the 147 remaining `test_v0NNN_*` / `test_cycleNN_*` /
`test_phase4_*` files. Each candidate ≤4 KB AND ≤8 tests AND has an obvious canonical
receiver (`test_query.py`, `test_compile.py`, `test_config.py`, `test_lint.py`,
`test_evolve.py`, `test_models.py`, `test_v070.py`, `test_capture.py`, `test_utils.py`,
or `test_mcp_core.py`).

**Pass:** 4 candidates listed in design doc with byte/test counts and target receivers.

### AC2 — Each fold preserves test count
Per fold: source file is deleted, all `def test_*` methods land in receiver. Total
test count after all 4 folds equals start count (3025).

**Pass:** `pytest --collect-only -q | tail -1` shows the same number before and after
the fold series.

### AC3 — Helper-name uniqueness preserved (Step-5 Q1 rule, cycle 50/51 precedent)
If a candidate brings a helper named `_install_X`, `_FakeY`, `_write_Z`, `_run_W`,
or `_<verb>_<noun>` that COULD collide with an existing helper in the receiver,
rename in-fold to `_<cycle53_distinguisher>_<original_name>` or merge into existing
helper if shapes are identical.

**Pass:** `grep -nE "^def _|^\s+def _" <receiver>` returns no duplicate names.

### AC4 — Host-shape preservation (C40-L5 + cycle 47-50 precedent)
Each fold matches the receiver's existing shape:
- Receiver uses bare-function-only with section comments → fold becomes bare functions
  under a new `# ── ... (cycle 53 fold) ─` section comment.
- Receiver uses class-only → fold becomes a new class.
- Receiver uses class+bare mix → fold matches the nearest neighbour's shape.

**Pass:** `git diff` shows no class introduced into a bare-only receiver and no bare
function introduced into a class-only receiver.

### AC5 — Per-fold revert-verify (C40-L3)
For each fold, after the file is deleted and tests are moved, ONE moved test is
revert-checked: introduce `assert False` in the moved test body, run `pytest -x` on
just that test, confirm FAIL, then restore the assertion. Demonstrates the moved
test is genuinely executing.

**Pass:** Cycle log records `revert-verify: pytest -x <new_target> → FAIL on assert False
→ restored → PASS` for each fold.

### AC6 — Per-fold isolation pytest (C51-L1)
Per C51-L1: every fold MUST run `pytest <receiver>::<new_target> -v` IN ISOLATION
before commit, not just `pytest <receiver>` full file. Isolation surfaces latent
test-ordering bugs the moved test was riding.

**Pass:** Cycle log records isolation pytest pass per fold.

### AC7 — Self-exclusion guards upgraded (C52-L1)
Per C52-L1: any fold candidate whose body contains `if py.name == "test_cycleNN_*.py":`
or similar source-filename literals (`os.path.basename(__file__) == "..."`,
`if file == __file__:`) MUST be upgraded to a self-referential form (`Path(__file__).resolve()`,
`Path(__file__).name`) atomically with the fold commit, NOT a follow-up.

**Pass:** `grep -nE "__file__|py\.name ==|os\.path\.basename" <picked_candidates>`
audit at AC1 surfaces any source-filename matches; design doc records the upgrade plan
or confirms none of the picked candidates trigger this rule.

### AC8 — Full pytest green
After all 4 folds committed, full pytest passes locally on Windows
(`pytest -q 2>&1 | tail -4` shows `N passed, M skipped` with N+M == 3025, zero failures).

**Pass:** Per Step 12 CI hard-gate (full suite + ruff check + ruff format --check).

### AC9 — Dep-CVE state re-confirmed
Re-run `pip-audit` + `gh api dependabot/alerts` against `main` HEAD. Confirm all 4
known open advisories (diskcache CVE-2025-69872 / ragas CVE-2026-6587 / litellm
GHSA-xqmj-j6mv-4862 / pip CVE-2026-3219) still have empty / blocked `fix_versions`.

**Pass:** BACKLOG.md re-confirm date strings updated 2026-04-28 → 2026-04-29 with
verbatim citations to `pip-audit --format=json` output and `pip index versions <pkg>`
shape.

### AC10 — Doc sync
- `CHANGELOG.md` `[Unreleased]` Quick Reference: cycle-53 entry (Items / Tests / Scope / Detail).
- `CHANGELOG-history.md`: full cycle-53 bullet entry.
- `BACKLOG.md`: M3 progress note updated with cycle 53 fold delta (225 → 221).
- `CLAUDE.md`: test count narrative + version pin if changed (none expected — test count
  preserved per AC2).
- `docs/reference/testing.md` + `docs/reference/implementation-status.md`: count narrative
  per C26-L2 + C39-L3 (test count preserved; file count drop only).
- `README.md`: tree-block "tests/  # N tests across M files" (M = 221 post-cycle).

**Pass:** Step 17 grep audit — no count drift; all sites in lockstep.

### AC11 — PR opened + 2-round review
Step 18: `gh pr create` from `worktree-cycle-53` to `main`. Step 20: R1 DeepSeek V4 Pro
(architecture / contract / synthesis) + R2 Codex via Agent (edge cases / dispatch
hygiene). R3 trigger only if R1+R2 surface ≥3 NIT-volume per cycle-23 L4.

**Pass:** PR comment thread captures R1 + R2 verdicts; merge proceeds when both APPROVE.

### AC12 — Self-review skill patch
Step 24: scorecard for steps 1..23 + 3 lessons (L1/L2/L3) appended to
`references/cycle-lessons.md` + index entries to `.claude/skills/dev-ds/SKILL.md`. If
no surprises, write that fact explicitly per Step-24 rule (clean scorecards have value).

**Pass:** `git log -1 --grep="docs(cycle 53):"` shows the self-review commit on `main`.

## Blast radius

Test files only — `tests/test_v0NNN_*.py` / `tests/test_cycleNN_*.py` deletes;
`tests/test_query.py` / `tests/test_compile.py` / `tests/test_config.py` /
`tests/test_lint.py` / `tests/test_evolve.py` / `tests/test_models.py` /
`tests/test_v070.py` / `tests/test_capture.py` / `tests/test_utils.py` /
`tests/test_mcp_core.py` additions. Doc updates per AC10 above. No `src/kb/`
production-code changes.

Per Step-5 design-gate rule: revertibility = high (each fold is a simple `git revert`
to restore the deleted source file from history). Internal-only blast radius. CI is
the proof of correctness.
