# Cycle 47 — Design Draft (pre-eval)

**For:** R1 DeepSeek architecture review + R2 Codex edge-case review.
**Branch:** cycle-47-batch
**Scope:** hygiene + verify + 3 small folds. Total work ~12 files.

## Problem recap

Continue Phase 4.5 HIGH #4 freeze-and-fold + dep-CVE re-verify + BACKLOG
hygiene + (best-effort) cycle-47+ Windows CI investigation. Cycle 46
prioritised LOW shim deletion; cycle 47 resumes fold + verify cadence.

## Approach (3 alternatives considered)

### A. Conservative fold-only (PICKED)
- 3 small fold candidates: cycle16_config_constants (38 LOC, 5 tests) →
  new test_config.py; cycle11_task6_mcp_ingest_type (78 LOC, 6 tests) →
  test_mcp_core.py; cycle14_save_frontmatter (139 LOC, 9 tests) →
  test_models.py.
- Net file delta: -3 + 1 (new test_config.py) = **-2 files** (245 → 243).
- Test count delta: 0 (preserve all 20 tests as classes/functions in destinations).
- Dep-CVE re-verify (mechanical, no bumps) + BACKLOG hygiene timestamps.
- Best-effort Windows CI investigation: refresh BACKLOG entry with
  frontier list (specific test files to instrument first); apply NO new
  skipif markers absent reproducer.

### B. Aggressive fold (REJECTED)
- Add cycle14_augment_key_order (214 LOC), cycle13_frontmatter_migration
  (682 LOC) for 5 total folds.
- Risk: 682-LOC fold pulls in many test classes; cycle 22/23 reload-leak
  classes (cycle-19 L2, cycle-20 L1) become much more likely to surface
  under full-suite ordering. Each fold is a regression risk.
- Cycle 46 was a "no fold" cycle; jumping to 5 folds is too much delta
  for one cycle.

### C. Production-side opportunistic patch (REJECTED)
- Phase 4.5 MEDIUM `config.py` god-module split is shippable in one
  cycle, BUT changes the import surface used by ~80% of `src/kb/`. Cycle
  22/23 reload-leak classes apply directly. NOT compatible with hygiene
  cycle scope.
- Phase 4.5 MEDIUM `kb.query.hybrid KB_DISABLE_VECTORS=1` env-var
  shim is small (~20 LOC) but introduces a new public knob that needs
  Step-2 threat-model assessment (env-var injection, conflict with
  existing `[hybrid]` extra). Not a fit for a hygiene cycle.

## Final scope (under R1/R2 review)

**Group A — dep-CVE re-verify (6 ACs, mechanical):** AC1 diskcache,
AC2 ragas, AC3 litellm wheel METADATA (1.83.14 still pins
click==8.1.8), AC4 pip GHSA-58qw still null-patched, AC5+AC6
Dependabot litellm GHSA-r75f / GHSA-v4p8 drift persists. NO bumps;
refresh BACKLOG timestamps from cycle-46 → cycle-47.

**Group B — Test fold (3 ACs, atomic):**
- **AC7** Fold cycle16_config_constants → new test_config.py
  (5 tests preserved as TestConfigConstants class). Constants under
  test: `QUERY_REPHRASING_MAX`, `DUPLICATE_SLUG_DISTANCE_THRESHOLD`,
  `CALLOUT_MARKERS`. Behaviour-only assertions; no inspect.getsource.
- **AC8** Fold cycle11_task6_mcp_ingest_type → test_mcp_core.py
  (6 tests preserved as TestKbCreatePageHintErrors class).
  Coverage: `kb_ingest`, `kb_ingest_content`, `kb_save_source` rejecting
  `comparison`/`synthesis` with `kb_create_page` hint per cycle-11 AC2
  same-class peer rule (cycle-11 L3).
- **AC9** Fold cycle14_save_frontmatter → test_models.py
  (9 tests preserved as 5 test classes:
  TestSaveFrontmatterInsertionOrder, TestSaveFrontmatterBodyVerbatim,
  TestSaveFrontmatterListValuedMetadataOrder,
  TestSaveFrontmatterExtraKeysPreserved, TestSaveFrontmatterAtomicWrite).
  Pinning `save_page_frontmatter` insertion-order + atomic-write contract
  per cycle-7 L1 (frontmatter sort_keys=False).

**Group C — Windows CI investigation (1 AC, best-effort):**
- **AC10** Read all tests using `threading.Thread`, `concurrent.futures`,
  `multiprocessing` from cycle 23-30 era. Identify candidates most likely
  to deadlock at `threading.py:355` on GHA windows-latest. Output
  refined BACKLOG entry with concrete frontier list (specific test IDs
  to instrument first) for cycle-48+. NO skipif markers applied without
  reproducer (cycle-36 L1 CI-cost discipline).

**Group D — BACKLOG hygiene (3 ACs):**
- **AC11** Update Phase 4.5 HIGH #4 progress note with cycle-47
  fold delta + cumulative remaining estimate.
- **AC12** Refresh ALL `(cycle-47+)` tagged entries with cycle-47
  re-confirmation timestamps.
- **AC13** Refresh dep-CVE timestamps (paired with AC1-AC6).

**Group E — Documentation (5 ACs):**
- **AC14** CHANGELOG.md cycle-47 Quick Reference entry.
- **AC15** CHANGELOG-history.md cycle-47 detail entry.
- **AC16** CLAUDE.md test count refresh (verify 3025 still accurate
  post-fold).
- **AC17** README.md tree-block test count (per C39-L3).
- **AC18** docs/reference/testing.md + implementation-status.md cycle 47
  history (per C26-L2 + cycle-35 extension).

**Total: 18 ACs across ~8 src+test files + ~6 doc files.**

## Risk assessment per AC

| AC | Risk class | Mitigation |
|---|---|---|
| AC1-AC6 | LOW (text-only) | Verification commands in threat-model.md; no bumps |
| AC7 | LOW (constants test) | New file; no canonical clobber risk; verify 5 tests preserved |
| AC8 | MEDIUM (MCP test fold) | Cycle-22 L3: full-suite ordering check post-fold; new TestClass scope avoids monkeypatch leakage between sibling tests |
| AC9 | MEDIUM (frontmatter fold) | Same as AC8; check `tmp_path` fixture isolation; verify 9 tests preserved |
| AC10 | LOW (text + grep only) | No code changes |
| AC11-AC13 | LOW (BACKLOG text) | Verify cycle-46 timestamps replaced consistently per cycle-46 L4 case-sensitive grep |
| AC14-AC18 | LOW (doc-sync) | Re-verify counts after R1/R2 fixes per cycle-15 L4 + C26-L2 + C39-L3 |

## CONDITIONS for Step 9 (open for R1/R2 critique)

1. **AC7-AC9 fold protocol:** for each fold, (a) read source verbatim,
   (b) paste into destination wrapped in cycle-stamped class, (c) delete
   the cycle file in same commit, (d) run `pytest <destination> -q`
   isolation, (e) re-run full suite to detect ordering issues.

2. **AC8 MCP-core fold:** the source's `_assert_create_page_error` helper
   is FILE-LOCAL — must NOT collide with any existing `_assert_*` helper
   in test_mcp_core.py. Rename to `_assert_create_page_error_for_alternative_type`
   or wrap inside the new class as a static helper.

3. **AC9 frontmatter fold:** test_models.py uses bare `def test_*` AND
   class-based tests. Fold as 5 new classes; do NOT promote the helper
   `frontmatter.Post` construction to module level (would clash with
   existing `frontmatter` import + cache fixture pattern).

4. **AC10 NO skipif markers:** absent reproducer, BACKLOG entry refresh
   only. Cycle-36 L1 CI-cost discipline — one new CI dimension per cycle;
   cycle 47 is hygiene-only, no new CI dimension.

5. **AC1-AC6 timestamps:** use `2026-04-28 (cycle-47 re-confirmed)` to
   distinguish from `2026-04-28 (cycle-46 re-confirmed)` on the same
   calendar day. The cycle stamp matters more than the date.

6. **AC8/AC9 isolation-vs-suite check:** per cycle-22 L3, run BOTH
   `pytest <destination_file> -q` AND `pytest -q | tail -3` after each
   fold commit. Isolation passes don't prove full-suite green.

## Open questions for R1/R2

Q1. Is folding cycle16_config_constants into a NEW test_config.py the
right call vs splitting between test_lint.py + test_query.py? The 3
constants split semantically: QUERY_REPHRASING_MAX = query, others = lint.
But splitting breaks the "constants module test cluster" pattern.

Q2. Does AC9's 5-class fold into test_models.py risk fixture-scope
collisions with the existing cache-clear fixture used by all
load_page_frontmatter tests? `tmp_path` is function-scoped so no, but
verify.

Q3. Should AC10 attempt actually applying skipif or strictly defer per
cycle-36 L1?

Q4. Phase 4.5 HIGH #4 progress note references "tests/ now 241 files"
(after cycle-44 net +1). Cycle 45 was 244, cycle-45 hotfix 243, cycle 46
"no new fold". Cycle 47 should land at 241 (243 → -3 folded + 1 new
test_config.py = 241). Verify the math is right at AC11.

Q5. Are there any dep-CVE entries OTHER than the 4 pip-audit + 2
Dependabot drift entries that need refresh? Re-grep BACKLOG.md for
"cycle-46 re-confirmed" stamps.
