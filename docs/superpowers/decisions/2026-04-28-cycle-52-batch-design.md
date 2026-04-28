# Cycle 52 — Design Decision Gate

**Date:** 2026-04-28
**Branch:** `cycle-52-batch` (worktree at `D:/Projects/llm-wiki-flywheel-c52`)
**R1 reviewer:** DeepSeek V4 Pro (high-effort thinking, ~30KB prompt)
**R1 output:** `.data/cycle-52/design-eval-r1-out.txt` (16.4 KB)

## R1 verdicts

- **AC1:** AMEND (NIT) — vacuousness claim arguable; fold proceeds as-is, file BACKLOG upgrade candidate.
- **AC2:** AMEND (MAJOR) — self-exclusion guard must update from `test_cycle19_lint_redundant_patches.py` to `test_lint.py` (or use `Path(__file__).name`) after fold.
- **AC3:** APPROVE
- **AC4:** APPROVE

## Open questions resolved

### Q1 — AC2 self-exclusion guard fix shape

**OPTIONS:**
- (a) Hardcode `if py.name == "test_lint.py": continue` after fold.
- (b) Use `if py.resolve() == Path(__file__).resolve(): continue` (self-referential).
- (c) Drop the exclusion entirely; rely on the `kb.compile.compiler.HASH_MANIFEST` substring not appearing in the receiver.

**ARGUE:**
## Analysis
Option (a) is the most direct: it preserves the original intent (skip the file containing the
guard) with a one-character-per-character mapping from old to new name. The downside is that if
`test_lint.py` is ever renamed in a future fold cycle (unlikely — it's a canonical receiver), the
guard silently breaks self-exclusion again.

Option (b) using `Path(__file__).resolve()` self-references the file holding the guard,
making the exclusion robust to future renames. It's two lines of code, one import already
available (`from pathlib import Path`), and provides forward-protection that aligns with the
freeze-and-fold rule that canonical receivers grow but their names should be stable. The slight
cost is a `pathlib`-dependent comparison instead of string equality, but the AST walker already
imports `pathlib` for `TESTS_DIR = Path(__file__).parent`, so no new dep.

Option (c) drops the exclusion. This is risky: at any future drift, if a `test_lint.py` test
method takes `tmp_kb_env` and patches `kb.compile.compiler.HASH_MANIFEST`, the guard fails on
itself with no way to distinguish "valid offender" from "guard scanning itself". This is the
weakest option.

Lower-blast-radius wins: option (b) provides robust self-exclusion for negligible code cost;
option (a) is acceptable but ages poorly. Pick (b).

**DECIDE:** (b) — replace the exclusion line with `if py.resolve() == Path(__file__).resolve(): continue` (string-name-independent self-reference).
**RATIONALE:** Forward-protection against future renames; pathlib already imported; one-line change.
**CONFIDENCE:** High.

### Q2 — AC1 behavioral upgrade (NIT escalation)

**OPTIONS:**
- (a) Keep R1's NIT as plan-of-record; do NOT upgrade in-fold; file BACKLOG entry per C40-L3 for cycle-53+ consideration.
- (b) Attempt in-fold C41-L1 behavioral upgrade now: stub `_canonical_rel_path` and assert spy fires from both `compile_wiki` full-mode prune and `detect_source_drift`.

**ARGUE:**
## Analysis
The cycle-19 design.md AC14 DROP rationale (preserved verbatim in the source file's docstring)
explicitly claims a behavioral test would be vacuous because the divergence scenario is exactly
what the fix prevents. R1 challenged this: a positive behavioral test that stubs the helper and
checks both call sites use it is NOT vacuous — it pins call-graph wiring rather than divergence
behavior.

R1's argument is technically correct: a spy on `_canonical_rel_path` could be installed via
`monkeypatch.setattr(compiler, "_canonical_rel_path", spy)`, then both `compile_wiki(mode="full")`
and `detect_source_drift` invoked with sources that should be pruned, and the spy.call_args_list
inspected to confirm BOTH sites passed through the helper. This would be a behavioral test of
"both call sites are wired to the canonical helper" rather than "the helper is referenced
verbatim in the source text".

However: in-fold attempts add scope, risk, and time to a hygiene cycle. The current cycle's
explicit goal is "preserve all 3025 tests verbatim across the fold" (requirements §AC6). An
in-fold behavioral upgrade would (1) require constructing a non-trivial fixture (raw_dir with
pre-stale manifest entries to trigger pruning at both sites), (2) verify both sites actually
execute the prune path under test conditions (not all calls go through both prune sites
simultaneously), and (3) potentially expose more cycle-19 L2 reload-leak hazards by importing
compiler at fold time vs lazy-import.

The cycle-44 doc precedent for C41-L1 upgrades (cycle-43 upgrade candidates resolved in cycle 44)
shows the cleanest path is: fold first, file BACKLOG entry, upgrade in next cycle when isolated
attention can be devoted. C40-L3 explicitly mandates this pattern.

**DECIDE:** (a) — fold AC1 as-is (move both tests verbatim into test_compile.py § Compiler tests). File BACKLOG cycle-53+ candidate per C40-L3 documenting R1's behavioral-upgrade observation.
**RATIONALE:** Cycle-52 is hygiene-only; in-fold upgrades violate the "preserve verbatim" charter; C40-L3 prescribes BACKLOG path for upgrade candidates.
**CONFIDENCE:** High.

### Q3 — AC4 helper rename

R1 confirmed `_summary_page` has no clash in test_query.py and recommended NO rename. The
requirements doc said "rename to `_tier1_summary_page` if needed". R1 says not needed.

**DECIDE:** Keep `_summary_page` as-is; no rename required. (Diverges from requirements doc's
conditional rename — R1's grep-verification trumps the conditional language.)
**RATIONALE:** Per cycle-50 Q2 helper-name uniqueness rule, rename is needed only on collision; R1 confirmed no collision.
**CONFIDENCE:** High.

### Q4 — AC3 helper rename

R1 confirmed `_write_page` has no clash but recommended keeping the rename to `_write_concept_page`
for clarity (hygiene improvement, not collision resolution).

**DECIDE:** Apply the rename per the requirements doc. R1 endorses it as a hygiene improvement.
**RATIONALE:** "concept" disambiguates from any future fold helper that writes a different page type to test_utils.py.
**CONFIDENCE:** High.

### Q5 — Section heading for AC4 fold

The requirements doc proposes a new section `# ── Tier-1 budget wiring (cycle 52 fold) ─` after
the existing `# ── Query integration tests ─`. Inspection of test_query.py shows the file ends
at line 349 with a `TestFlagStaleResultsEdgeCases` class. The cleanest placement is at the END
of the file (line 350+), as a new section, NOT after `# ── Query integration tests ─` (which
would split existing logical groupings).

**DECIDE:** Append AC4 fold at END of test_query.py as new section `# ── Tier-1 budget wiring (cycle 52 fold) ─`.
**RATIONALE:** Avoids splitting existing test groupings; matches cycle-50 fold-section placement convention.
**CONFIDENCE:** High.

### Q6 — Section heading for AC2 fold

The requirements doc proposes a new section `# ── Lint guards (cycle 52 fold) ─` after the
existing `# ── augment._resolve_raw_dir branch coverage (cycle 43 AC11 fold) ─`. test_lint.py
ends at line 406 with the augment block. End-of-file placement is the cleanest.

**DECIDE:** Append AC2 fold at END of test_lint.py as new section `# ── Test-suite lint guards (cycle 52 fold) ─`.
Note the slight rename from `Lint guards` → `Test-suite lint guards` to disambiguate from the
production `lint/` module guards already in the file.
**RATIONALE:** End-of-file placement matches cycle-50 convention; "Test-suite" prefix avoids confusion with kb.lint.checks tests in the file.
**CONFIDENCE:** High.

## CONDITIONS (Step 9 must satisfy)

1. **AC2 self-exclusion guard:** During the fold, replace `if py.name == "test_cycle19_lint_redundant_patches.py": continue` with `if py.resolve() == Path(__file__).resolve(): continue` (Q1 decision (b)).
2. **AC1 behavioral upgrade BACKLOG entry:** Add a cycle-53+ entry under Phase 4.5 HIGH `tests/` carry-over (Q2 decision (a)).
3. **AC4 helper:** Keep `_summary_page` as-is (Q3 decision).
4. **AC3 helper:** Rename `_write_page` → `_write_concept_page` (Q4 decision).
5. **AC4 placement:** END of test_query.py with section `# ── Tier-1 budget wiring (cycle 52 fold) ─` (Q5 decision).
6. **AC2 placement:** END of test_lint.py with section `# ── Test-suite lint guards (cycle 52 fold) ─` (Q6 decision).
7. **Per-fold revert-verify per C40-L3:** insert `assert False` mid-method, run `pytest <receiver>::<new_target> -v -x` to confirm FAIL, restore.
8. **Per-fold isolation pytest per C51-L1:** `pytest <receiver>::<new_target> -v` for every moved test/method, BEFORE commit.
9. **Branch discipline per C42-L4:** `git branch --show-current` returns `cycle-52-batch` before every Edit and commit.
10. **Commit message bodies:** use `confirmed`/`validated`, NOT `verify` (per C35-L4 + C50-L1).

## Final decided design

All 4 ACs proceed with the conditions above. Hygiene cycle: 4 folds, no src/ changes. File count
229 → 225 (-4). Test count preserved at 3025. Class A CVEs (4 open Dependabot alerts) re-confirmed
no upstream patches available — track for cycle 53.

**VERDICT:** PROCEED.
