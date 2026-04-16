# Opus Scope Decision Gate — Backlog Comprehensive Fix

**Date:** 2026-04-15
**Feature:** Comprehensive BACKLOG.md bug resolution
**Gate:** Pre-brainstorming scope decomposition (not yet Step 1.6 design gate)
**Sub-agent model:** Opus
**Verdict:** `APPROVE-WITH-CONDITIONS` (amended 2026-04-15 — see Second-Gate Review at bottom)

## Context

User invoked `/feature-dev` with the literal request "comperasive reslove all the bugs within backlogs and fix with prop tests and code reviews" (comprehensive resolution of all BACKLOG.md bugs with proper tests and code reviews).

BACKLOG.md has 422 open items across 5 audit phases. This is weeks of work and would produce an unreviewable PR if attempted in one cycle. Scope must be decomposed BEFORE entering the design-brainstorming flow.

## Summary

**AMENDED (2026-04-15 second-gate review):** First `/feature-dev` cycle = Phase 4.5 CRITICAL Themes 1–4 only (16 items). Theme 5 (docs-sync, 2 items) deferred to an immediately-following docs-sync PR. All remaining 372 items (Phase 4.5 HIGH/MEDIUM/LOW, Phase 5 pre-merge, Phase 5 community proposals) are deferred to subsequent cycles.

## Decisions

### Q1 — Scope: `A. Phase 4.5 CRITICAL only (~18 items)` (Confidence: HIGH)

**Rationale:** The user's literal request (Option E — 422 items) trips CLAUDE.md's *"Two tests before declaring done"* principle: a 422-item PR cannot satisfy "every changed line traces to the request" (reviewer fatigue destroys the trace) and fails "would a senior engineer say this is overcomplicated?" The user's intent ("fix all bugs with tests and code review") is honored over MULTIPLE cycles, not one.

Option C (theme-cluster of 8) would split CRITICAL into two PRs with no concrete benefit; CRITICAL is already the smallest semantically-coherent unit the BACKLOG itself defines. Option D bundles two unrelated audit scopes and forces cross-branch reasoning. Option B's ~78-item PR is the biggest temptation but crosses the reviewability line (estimated 3500+ LOC diff) — and a HIGH fix landed on top of unfixed CRITICAL test-isolation gives false confidence because tests pass against polluted production state.

### Q2 — Bundling Strategy: `root-cause-theme` (Confidence: HIGH)

5 natural theme clusters matching BACKLOG.md's own groupings:

1. **Test-isolation** (5 items) — tests mutate production `wiki/`, assertions skipped silently
2. **Contract-consistency** (4 items) — result dict shape drift, internally-inconsistent reports
3. **Data-integrity** (5 items) — CJK slug collapse, whitespace wikilinks, concurrency RMW losses
4. **Error-chain** (2 items) — `from e` missing, `last_error` not updated
5. **Docs/version drift** (2 items) — three version strings live at once, stale stats

### Q3 — Test Policy: `per-bug regression MANDATORY for 16 code fixes; pre-commit verification script for 2 docs-drift items` (Confidence: HIGH)

CLAUDE.md Working Principles line 15–16 is the project convention: *"Fix the bug" → "Write a failing test that reproduces it, then make it pass."*. Every backlog item has a concrete fix hint that doubles as a test assertion. Docs-drift items get a pre-commit verification script instead of a pytest regression (substance over ritual).

### Q4 — Rollback Granularity: `one commit per theme-bundle` (5 commits inside the PR) (Confidence: MEDIUM)

5 themed commits = 5 rollback points. Matches Q2 bundling; each commit has a coherent story at `git log` level.

## Conditions (must be enforced during implementation)

1. **Test-isolation theme ships in the FIRST commit of the PR.** All subsequent theme fixes must have regression tests written AFTER those isolation fixes land (tests must use `tmp_wiki`/`tmp_project` fixtures with `wiki_dir=` threaded through).
2. **Items 8 and 9 (`lint/runner.py` `run_all_checks`) ship in the same subagent task.** Ordering: item 8 (sentinel mutation) first so item 9's re-scan sees clean state.
3. **Items 10 and 13 (`review/refiner.py`) ship in the same subagent task** to avoid merge conflicts.
4. **Item 14 (double manifest write) has a known interaction with Phase 4.5 HIGH item `pipeline.py:91-113` (`_is_duplicate_content` race).** The CRITICAL fix drops the double-write; the HIGH fix adds proper locking. Plan MUST leave a `# TODO(phase-4.5-high)` inline comment so next-cycle HIGH fix targets the post-CRITICAL code shape.
5. **Item 4 (version drift) does NOT bump version** — re-align `pyproject.toml` to `0.10.0` (matching `__init__.py:3`), update README badge. Version bump is a separate release-PR concern.
6. **CHANGELOG.md entry** lands under `[Unreleased]` under a new subheading `### Fixed — Phase 4.5 CRITICAL (18 items)`. No version bump.
7. **Item 5 (stats drift)** is a moving target — compute test count as the final commit of the PR via `pytest --collect-only -q | tail -1`. Not alongside Theme 1.

## Enumerated Backlog Items in Scope (all 18)

### Theme 1: Test-isolation (5 items) — first commit

1. `tests/test_ingest.py:124-132` — mock omits `WIKI_CONTRADICTIONS`, mutates production `wiki/contradictions.md`
2. `tests/test_v0917_contradiction.py:12-30` — empty-list allows 4 `assert "key" in item` to be silently skipped
3. `tests/test_phase4_audit_security.py:37-45` — only `"too large" not in result.lower()`; passes on any error
7. `query/engine.py:357` — `search_raw_sources` hardcoded `RAW_DIR`; leaks prod `raw/` in tests
8. `lint/runner.py:80-98` — `check_orphan_pages` mutates `shared_graph` with sentinel nodes

### Theme 2: Contract-consistency (4 items)

6. `ingest/pipeline.py:565-576` — duplicate-branch result dict missing keys; `KeyError` on downstream
9. `lint/runner.py:53-78` — `run_all_checks(fix=True)` has checks running on pre-fix state
10. `review/refiner.py:111` — `updated_content.lstrip()` silently strips indented code blocks
17. `utils/llm.py:262-270` — `call_llm_json` no-tool-use case discards leading text block

### Theme 3: Data-integrity (5 items)

11. `utils/text.py:128` — `slugify` `flags=re.ASCII` collapses CJK/emoji to empty string
12. `utils/markdown.py:5` — `WIKILINK_PATTERN` accepts `[[   ]]` whitespace-only; phantom nodes
13. `review/refiner.py:13,120-133` — `_history_lock = threading.Lock()` without `file_lock`; cross-proc audit loss
14. `compile/compiler.py:343-347 + ingest/pipeline.py:686-688` — double manifest write races
15. `utils/io.py:74-99` — `file_lock` SIGINT gap leaves orphan lock file

### Theme 4: Error-chain (2 items)

16. `utils/llm.py:85-110` — `APIStatusError` non-retryable raise without `last_error = e`
18. `ingest/pipeline.py:553-559` — `raise ValueError(...)` without `from e`; wipes byte-offset diagnostic

### Theme 5: Docs/version drift (2 items) — **DEFERRED by second-gate review**

~~4. `pyproject.toml:3` vs `src/kb/__init__.py:3` vs `README.md:7` — three different version strings~~
~~5. `CLAUDE.md:13, 131, 255` — stats drift; add `scripts/verify_docs.py` verification~~

**Deferred to immediately-following docs-sync PR.** See Second-Gate Review below.

## Deferred to Subsequent Cycles

| Phase | Items | Cycle |
|---|---|---|
| **Phase 4.5 CRITICAL docs-sync (Theme 5)** | **2** | **Immediately after current PR merges** |
| Phase 4.5 HIGH | ~60 | Cycle 2 |
| Phase 4.5 MEDIUM | ~150 | Cycle 3 |
| Phase 4.5 LOW | ~60 | Cycle 4 (or opportunistic) |
| Phase 5 pre-merge (kb-capture R1/R2/R3) | ~50 | Separate cycle (branch-scoped) |
| Phase 5 pre-merge (kb-lint-augment) | ~10 | Separate cycle |
| Phase 5 community followup proposals | ~50 | NOT bugs — feature track |

## Notes for Next Steps (writing-plans)

- **4 subagent tasks** (one per Theme 1–4), dispatched serially (Theme 1 MUST land first; Themes 2–4 can be parallel but share `ingest/pipeline.py` so serial is lower-risk).
- Each subagent receives: theme's items, test policy, theme-specific constraints from Conditions section.
- **Revised LOC:** ~150 production + ~400 tests + CHANGELOG ≈ 700 LOC net PR size (Theme 5's ~100 LOC moves to follow-up PR).
- CHANGELOG entry: append to `[Unreleased]` under `### Fixed — Phase 4.5 CRITICAL (16 items)`; no version bump. The 2 Theme 5 items get their own `[Unreleased]` entry in the immediately-following docs-sync PR.

## Second-Gate Review (2026-04-15, adversarial Opus)

A second Opus gate was dispatched to adversarially stress-test the inclusion of Theme 5 (docs/version drift, Items 4 and 5) in the first `/feature-dev` cycle's PR. Verdict: **OVERRIDE to DEFER**.

**Decisive argument:** Item 5 includes adding `scripts/verify_docs.py` + pre-commit wiring — preventive infrastructure, not a bug fix. This trips CLAUDE.md Working Principles lines 21–23 ("every changed line should trace directly to the request" / "drop drive-by edits"). Condition 7's moving-target workaround is itself evidence of scope conflation — when a condition exists only to rescue a bundling decision, the bundle is wrong.

**Cleanest resolution:** ship Themes 1–4 (16 CRITICAL code fixes) in the current PR; ship Theme 5 (Items 4 + 5, docs sync + verify script) in an immediately-following docs-sync PR once final test/module counts are frozen.

**The prior gate was correct about CRITICAL-only scope and root-cause theming; it underweighted the drive-by-edit concern for Theme 5's infrastructure component.**

### Deltas to prior decision

- **Scope**: 18 items → 16 items in this PR; 2 items moved to immediate follow-up PR.
- **Themes in this PR**: 5 → 4.
- **PR size**: ~1100 LOC → ~700 LOC.
- **Conditions dropped from this PR** (move to follow-up PR):
  - Condition 5 (version alignment): Item 4 moves to docs-sync PR.
  - Condition 7 (moving-target test count): docs-sync PR sees final numbers as fixed input, not moving input.
- **Condition 6 (CHANGELOG `[Unreleased]` placement)**: stays, but scope narrows to 16 items; 2 docs-sync items get their own `[Unreleased]` entry in the follow-up PR.
- **New follow-up action**: create a named tracking entry (GitHub issue or `BACKLOG.md` section) titled "Docs-sync PR: Item 4 (version drift) + Item 5 (stats drift + verify_docs.py)" scheduled for merge immediately after the current PR lands, so the small docs PR doesn't get deprioritized.
