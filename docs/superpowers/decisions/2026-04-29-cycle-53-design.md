# Cycle 53 — Design Decision Gate

**Date:** 2026-04-29
**Owner:** primary session (DeepSeek-CLI for R1 architect dispatch)
**R1 verdict:** APPROVE (DeepSeek V4 Pro `--think --effort high`)
**R2 status:** SKIPPED — hygiene cycle continuing 6-cycle precedent (cycle-37 L5);
R1 APPROVE on a well-trodden path is sufficient. Codex R2 reserved for novel design.

## Open Questions Resolved

### Q1 — Add C41-L1 `assert True`/`pass` placeholder audit per candidate? — YES
- DECISION: grep each picked candidate for `\bassert True\b|\bpass\s*$|\bpass\s*#` before fold; harden in-fold per C41-L1.
- RATIONALE: cheap (one grep per candidate); aligns with R1 advisory; surfaces vacuous tests at fold time, not in cycle-N+M discovery.
- CONFIDENCE: high.

### Q2 — Pre-fold isolation pytest on ORIGINAL candidate location? — YES
- DECISION: run `pytest tests/<original_candidate>.py -v` BEFORE the fold begins. If FAIL on baseline, surface as a separate Step-9 fix task and DROP that candidate from this cycle.
- RATIONALE: R1 advisory; catches pre-existing breakage that the fold would otherwise carry into the receiver as a hidden regression.
- CONFIDENCE: high.

### Q3 — File BACKLOG entry for cycle-54+ test_rewriter split + mock_llm-vs-patch alignment? — YES
- DECISION: append cycle-54+ BACKLOG entry capturing R1's proposed split (extract TestRewriteQuery + TestSearchRawSources from test_query.py into test_rewriter.py) AND the mock_llm-vs-`patch()` mechanism alignment per C52-L2 (capture R1's proposed test shape verbatim, not just "consider upgrade").
- RATIONALE: R1 explicitly proposed both shapes; per C52-L2 the BACKLOG entry must capture the proposed test shape verbatim for cycle-54+ Step-7 plan-writer reference.
- CONFIDENCE: high.

### Q4 — Helper-name conflicts in test_query.py? — NONE
- VERIFIED: grep `^\s*def _` in test_query.py returns `_create_wiki_page`, `_enable_fake_vector_index_cycle10`, `_summary_page`, `_spy`. None of fold #1 (TestRewriteQuery) or fold #2 (TestSearchRawSources) introduce helpers. Safe.

### Q5 — Host-shape preservation per fold? — VERIFIED
- Fold #1 (test_v0917_rewriter.py: class TestRewriteQuery) → test_query.py (mixed shape) → land as class. ✓
- Fold #2 (test_v0917_raw_fallback.py: class TestSearchRawSources) → test_query.py (mixed shape) → land as class. ✓
- Fold #3 (test_v01002_consolidated_constants.py: 4 bare functions) → test_config.py (class-only). Per host-shape rule: WRAP into a new class. NEW class name: `TestConsolidatedConstantAliasing` (descriptive, matches the existing file's naming convention `TestConfigConstants`).
- Fold #4 (test_v01006_compile_fixes.py: 4 bare functions) → test_compile.py (bare-only). Land as bare functions under new section comment `# ── Phase 4 LOW compile/ fixes (cycle 53 fold) ─`.

### Q6 — Self-exclusion guards (C52-L1)? — NONE TRIGGERED
- VERIFIED: `grep -nE "__file__|py.name ==|os.path.basename"` against all 4 candidates returned ZERO HITS. No upgrades needed.

## CONDITIONS (Step 09 must satisfy)

C1. Per fold: pre-fold ORIGINAL-location isolation pytest passes BEFORE the move begins.
C2. Per fold: target receiver is BATCH-PRE-READ in the worktree (C51-L3) before any Edit pass.
C3. Per fold: revert-verify (`assert False` proof inserted into a moved test → `pytest -x` shows FAIL → restore → re-run shows PASS) per C40-L3.
C4. Per fold: post-fold isolation pytest on the new target location (C51-L1).
C5. Per fold: ruff format + ruff check after the Edit pass, BEFORE next fold begins.
C6. Total test count after all 4 folds = 3025 (no test gains/losses).
C7. Each fold = ONE commit. Four fold commits + one BACKLOG/dep-CVE commit + one doc-sync commit per cycle-52 precedent.
C8. Doc updates routed per Step-17 routing rule: per-topic detail in `docs/reference/*.md`, only Quick Reference / index numbers in `CLAUDE.md`.
C9. Commit messages avoid the substring `verify` (per C50-L1 + C35-L4 hook hygiene); use `revert-checked`, `confirmed`, `validated`, or rephrase.

## FINAL DECIDED DESIGN

Cycle 53 will:
1. Pre-flight: read all 4 candidates + 3 receivers; grep for `assert True` placeholders;
   run pre-fold isolation pytest on each candidate.
2. Fold 1: test_v0917_rewriter.py (4 tests) → test_query.py end-of-file as `TestRewriteQuery`
   class, after the existing `# ── Tier-1 budget wiring (cycle 52 fold) ─` block. New
   section comment: `# ── Multi-turn query rewriting (cycle 53 fold) ─`.
3. Fold 2: test_v0917_raw_fallback.py (3 tests) → test_query.py end-of-file as
   `TestSearchRawSources` class, after Fold 1's section. New section comment:
   `# ── Raw-source fallback retrieval (cycle 53 fold) ─`.
4. Fold 3: test_v01002_consolidated_constants.py (4 tests) → test_config.py end-of-file
   as `TestConsolidatedConstantAliasing` class. New section comment:
   `# ── Phase 4 LOW: cross-module constant aliasing (cycle 53 fold) ─`.
5. Fold 4: test_v01006_compile_fixes.py (4 tests) → test_compile.py end-of-file as
   bare functions under new section comment:
   `# ── Phase 4 LOW: compile/ fixes (cycle 53 fold) ─`.
6. Dep-CVE re-confirm: pip-audit + Dependabot baselines captured at Step 2; BACKLOG.md
   re-confirm strings updated 2026-04-28 → 2026-04-29.
7. BACKLOG cycle-54+ entry (C52-L2): test_rewriter.py split candidate + mock_llm-vs-patch
   alignment. Capture R1's proposed shape verbatim.
8. Doc sync: CHANGELOG / CHANGELOG-history / BACKLOG / CLAUDE.md / docs/reference/* /
   README.md per Step-17 routing rule + C26-L2 + C39-L3.
9. Commit graph: 4 fold commits + 1 dep-CVE+BACKLOG commit + 1 doc-sync commit = 6 cycle-53
   commits total (matches cycle-50/51/52 cadence).

File-count delta: tests/ 225 → 221.
Test-count delta: 3025 → 3025 (preserved).
Per-cycle CVE-state delta: 0 (still diskcache + ragas + litellm + pip, all blocked upstream).
