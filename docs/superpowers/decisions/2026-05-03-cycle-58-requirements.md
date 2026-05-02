# Cycle 58 — Requirements

**Date:** 2026-05-03
**Branch:** `worktree-cycle-58` (worktree at `.claude/worktrees/cycle-58`)
**Trial-relevance:** fourth dev-mimo-opus trial cycle (after 55 + 56 + 57). Parallel to in-flight cycle 53 (4 folds, worktree only) and cycle 54 (`.gitignore` only, near-noop).

## Problem

`tests/` directory still contains 133 of 210 versioned test files (`test_v0NNN_*.py`, `test_phaseN_*.py`, `test_cycleN_*.py`) per the open BACKLOG HIGH item "tests/ coverage-visibility". Cycles 38-57 folded 30+ files via the freeze-and-fold pattern; the cadence (4-5 folds per cycle) needs to continue or the long-tail of versioned files becomes harder to discover, plumb, and review.

After cycle 57's merge (commit `92752c4`) main is clean at 208 files / 3021 tests. Cycle 53's 4 folds are still local in worktree (4 receivers: `test_query.py`, `test_config.py`, `test_compile.py` × 2). Cycle 54 has only a `.gitignore` change.

## Non-goals

- No new src/ behaviour changes. This is a test-fold/hygiene cycle.
- No CI matrix expansion (windows-latest still deferred per cycle-36 L1 + cycle-57 carry-over).
- No coverage-percent threshold adjustment.
- No Phase 5 / Phase 6 scope.
- No second pass at the cycle-57 batch — cycle 57 merged clean; only the open BACKLOG HIGH "freeze-and-fold" remains the steady-state work.

## Acceptance criteria (5 ACs + standing dep-CVE re-confirm)

| AC | Description | Receiver | Source LOC | Tests | Helper rename |
|----|-------------|----------|-----------:|------:|---------------|
| AC1 | `test_cycle17_mcp_tool_coverage.py` (5 classes, 13 tests, MCP-tool coverage probes for `kb_stats` / `kb_graph_viz` / `kb_verdict_trends` / `kb_detect_drift` / `kb_compile_scan`) → `tests/test_mcp_core.py` | `test_mcp_core.py` | 110 | 13 | none |
| AC2 | `test_cycle18_sanitize.py` (16 bare functions, `kb.utils.sanitize.sanitize_text` + `sanitize_error_text` + `_ABS_PATH_PATTERNS`) → `tests/test_utils_text.py` wrapped in new class `TestSanitizePathRedaction` to disambiguate from existing `yaml_sanitize` test prefix `test_sanitize_*` | `test_utils_text.py` | 116 | 16 | wrap-in-class to avoid name collision (cross-feature in shared receiver per cycle-50 cross-module hosting analogue) |
| AC3 | `test_cycle18_wiki_log.py` (5 bare functions, `kb.utils.wiki_log.rotate_if_oversized` + `append_wiki_log` rotate-inside-lock contract) → `tests/test_utils.py` § `# ── append_wiki_log ──` continuation; new section `# ── wiki_log rotation (cycle 58 fold) ─` end-of-file | `test_utils.py` | 126 | 5 | none (existing `test_rotate_*` names unique vs current receiver) |
| AC4 | `test_cycle15_lint_status_mature.py` (3 classes: `TestMatureStale`, `TestOtherStatusesIgnored`, `TestTodayOverride`; 8 tests; 1 helper `_write_page`) → `tests/test_lint.py` ; rename helper `_write_page` → `_write_status_mature_page` per C52-L4 helper-name uniqueness (cycle-52 `_write_concept_page`, cycle-56 `_write_phase4_concept_page` already exist in tests/) | `test_lint.py` | 112 | 8 | `_write_page` → `_write_status_mature_page` |
| AC5 | `test_cycle17_capture_two_pass.py` (2 classes: `TestAC10TwoPassWrite`, `TestAC10RollbackHelpers`; 10 tests; 1 helper `_make_items`) → `tests/test_capture.py` ; rename helper `_make_items` → `_make_two_pass_items` per C52-L4 (more specific name; no collision today, but cycle-prefix discipline applies) | `test_capture.py` | 220 | 10 | `_make_items` → `_make_two_pass_items` |
| AC6 (standing) | Dep-CVE baseline re-confirm: 4 unresolved CVEs from cycle-57 baseline (diskcache 5.6.3 GHSA-w8v5-vhqr-4h9v, ragas 0.4.3 GHSA-95ww-475f-pr4f, litellm 1.83.0 GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g blocked by `click==8.1.8` transitive pin, pip 26.0.1 GHSA-58qw-9mgm-455v) — verify still no upstream patches; do NOT attempt litellm 1.83.7 patch (cycle-55 already proved it introduces a different PR-CVE class B regression on python-dotenv) | (no fold) | 0 | 0 | n/a |

**Per-fold contract (applies to AC1-AC5):**
- Each fold preserves the source's test count exactly (no add, no drop, no rename of test methods unless a class-wrap is used; class-wrap method names re-derive from source method names).
- Each fold revert-verified per C40-L3 (`assert False` proof on a moved method shows pytest -x FAIL on the fold receiver).
- Each fold per-isolation pytest passes (`pytest tests/test_<receiver>.py -q`).
- Source file deleted in same commit.
- Per-fold isolation pytest passes (no failure introduced into other tests).

**Total fold deltas:**
- File count: 208 → 203 at branch HEAD (subject to Step 21 rebase if cycle 53/54 merge first).
- Test count: 3021 → 3021 (preserved across all 5 folds).

## Blast radius

| Layer | Module/file | Touched? | Risk |
|-------|-------------|----------|------|
| `src/kb/` production | none | NO | Test-fold cycle has zero `src/` diff |
| `tests/` | 5 sources DELETED, 5 receivers EDITED (test_mcp_core.py, test_utils_text.py, test_utils.py, test_lint.py, test_capture.py) | YES (additive within receivers) | Low — class/helper-rename discipline per C52-L4; per-fold isolation pytest gate |
| Docs | CHANGELOG.md (Quick Reference brief), CHANGELOG-history.md (per-cycle detail), CLAUDE.md (test-count + file-count Quick Reference), docs/reference/testing.md, docs/reference/implementation-status.md (cycle 58 narrative), BACKLOG.md (no resolutions; HIGH item remains open) | YES (Step 17) | Low — established C26-L2-extended doc-grep across CLAUDE.md + docs/reference/ |
| CI | none (no workflow change) | NO | n/a |
| Deployable artifacts | none | NO | n/a |

**Collision-avoidance with parallel cycles (per cycle-56 picks-marker convention):**

| Receiver | Cycle 53 (in-flight) | Cycle 54 (`.gitignore` only) | Cycle 58 |
|----------|----------------------|-------------------------------|----------|
| `test_mcp_core.py` | – | – | **AC1 (yes)** |
| `test_utils_text.py` | – | – | **AC2 (yes)** |
| `test_utils.py` | – | – | **AC3 (yes)** |
| `test_lint.py` | – | – | **AC4 (yes)** |
| `test_capture.py` | – | – | **AC5 (yes)** |
| `test_query.py` | yes (2 folds) | – | NO |
| `test_config.py` | yes (1 fold) | – | NO |
| `test_compile.py` | yes (1 fold) | – | NO |
| `test_models.py` | – | yes (.gitignore + ?) | NO |

All 5 cycle-58 receivers are disjoint from cycle 53 and cycle 54 — clean merge ordering regardless.

## Standing dep-CVE re-confirm (carry-over from cycle 57 + earlier)

Per cycle-22 L4 + cycle-49+ standing pattern:
1. `pip-audit` (live venv, `--no-deps` per C34-L1) — should still report 4 vulns matching cycle-57 baseline.
2. `gh api` Dependabot alerts — should still match cycle-57 baseline (≥2 GHSA-r75f / GHSA-v4p8 alerts present).
3. If any advisory dropped a fix between 2026-05-02 (cycle 57) and 2026-05-03 (cycle 58 start), Step 15 patches it.
4. If any new advisory landed (cycle-22 L4 cross-cycle arrival), Step 14 (b) blocks per Class B PR-introduced rule even though our diff doesn't touch deps.

Document the baseline diff in Step 14 narrative; preserve `.data/cycle-58/cve-baseline.json` + `.data/cycle-58/alerts-baseline.json` per cycle-22 L1 Windows-bash artifact-path convention (project-relative paths, not `/tmp/`).

## Step-execution strategy

- **Steps 1-5** (req + threat + brainstorm + design + decision): primary session per C37-L5 (cycle has 5 small folds + 1 standing dep-CVE; primary holds full context from cycle-57 batch).
- **Step 6** (Context7): SKIP — no third-party API surfaces touched, pure stdlib + internal kb.* modules.
- **Step 7** (impl plan): primary session per C14-L1 / C37-L5 sizing heuristic (≤15 ACs, primary holds context).
- **Step 8** (plan gate): MiMo Coding subagent per skill workflow.
- **Step 9** (impl): primary session per C13-L2 + C37-L5 (5 small mechanical folds, ≤220 LoC each, no novel APIs).
- **Step 10** (simplify): SKIP — pure rename/move (no behaviour change to simplify); record no-op.
- **Step 11** (SAST): SKIP — test-fold/hygiene cycle (no `src/` diff).
- **Step 12** (CI hard gate): full pytest + ruff + pip-audit per skill.
- **Step 13** (coverage delta): SKIP-when partially applies (test-fold cycle); confirm no coverage regression on receivers.
- **Step 14** (security verify): MiMo Coding subagent verifies threat model + PR-CVE diff.
- **Step 15** (existing-CVE patch): standing re-confirm (no patches expected between 2026-05-02 → 2026-05-03).
- **Step 16** (IaC + container + SBOM): all sub-steps SKIP.
- **Step 17** (docs): DeepSeek subagent per skill (mechanical doc work; preserves Token-Plan credits for impl/plan/verify steps).
- **Step 18** (PR): MiMo Coding subagent per skill.
- **Step 19** (signed commits + attestation): SKIP — no signing policy + no published artifact.
- **Step 20** (PR review): cross-vendor R1 (DeepSeek + Sonnet) → R2 (Codex + Sonnet) per user-decreed cross-vendor diversity.
- **Step 21** (merge + late-arrival CVE warn): standard.
- **Steps 22-23** (deploy + smoke): SKIP — no deployable artifact.
- **Step 24** (self-review + skill patch): mandatory scorecard; lesson synthesis triggered (3+ PRs since cycle-55 last patch — cycle 56, 57 trial run + this is the 4th trial).

## Trial-data capture (May 2026 MiMo trial)

Per project_mimo_may2026_trial.md, surface notable mimo* outcomes:
- Step 8 plan gate dispatch (`mimocoding-rescue` @ `mimo-v2.5-pro`) — measure latency, identity-confusion, TOS routing.
- Step 14 security verify dispatch (`mimocoding-rescue` @ `mimo-v2.5-pro`).
- Step 18 PR finalize dispatch (`mimocoding-rescue` @ `mimo-v2.5`).
- Step 17 doc update dispatch (`deepseek-rescue` @ `deepseek-v4-pro`) — preserves Token-Plan budget per skill rationale.
- Step 20 R1 DeepSeek + R2 Codex per cross-vendor mandate.

Record latencies + verdicts for the 2026-05-31 writeup.
