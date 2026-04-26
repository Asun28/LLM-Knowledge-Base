# Cycle 37 — Self-Review Scorecard + Skill Patches

**Date:** 2026-04-26
**Cycle:** 37 — POSIX symlink security fix + requirements split
**PR:** #51 (squash-merged at `b95638c`); branch `feat/backlog-by-file-cycle37` deleted at merge.
**Verdict:** SHIPPED — closed 2 of 7 cycle-37 BACKLOG candidates filed at cycle-36 close. Production POSIX security gap fixed; requirements file split landed additively. ZERO new CI dimensions per cycle-36 L1.

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | yes | pip-audit prepends a status line ("Found N known vulnerabilities...") to its JSON stdout — needed `text[text.index('{'):]` to parse. Also seen in cycle 36; refines C35-L1 (binary invocation) with a parsing nuance. |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval (R1+R2) | yes | yes | Q3 surfaced naturally during R1: original AC7 "shim" approach would re-introduce version drift; backward-compat principle led to AC7-AMENDED "unchanged". Refines cycle-36 L3 (post-pivot doc-accuracy) — same "additive vs replacement" principle. |
| 5 — Decision gate | yes | yes | All 6 questions resolved primary-session in <10 min. Cycle-36 L2 validated again. |
| 6 — Context7 | skipped | n/a | Pure stdlib (pathlib) + project tooling (pip resolver) — no third-party API to look up. |
| 7 — Plan | yes | yes | Wrote in primary per cycle-14 L1 + cycle-36 L2. ~5 min vs. ~10 min Codex dispatch. |
| 8 — Plan gate | yes | yes | Self-gated in primary per cycle-21 L1. All 9 ACs covered, all 7 threats mapped, no PLAN-AMENDS-DESIGN flags. |
| 9 — TDD implementation | yes | yes | All 5 tasks within cycle-13 L2 sizing thresholds; primary-session faster than dispatch. Total ~25 min for 9 ACs. |
| 9.5 — Simplify | skipped | n/a | `src/` diff < 50 LoC (single 9-line reorder in context.py). Per Step-9.5 skip-when. |
| 10 — CI hard gate | yes | yes | 2991 passed + 21 skipped + 0 failed. Ruff check + format both clean. ~141s wall time. |
| 11 — Security verify | yes | yes | All 7 threats IMPLEMENTED. PR-CVE diff INTRODUCED set empty. |
| 11.5 — CVE patch | skipped | n/a | Same 4 Class-A alerts as cycle 36; all blocked at click<8.2 or null upstream fix. |
| 12 — Doc update | yes | yes | CHANGELOG + history + CLAUDE.md test-count + docs/reference/* mirrors + BACKLOG cleanup. Two cycle-37 entries deleted as resolved; 5 remaining re-pinned to cycle-38+. |
| 13 — PR finalize | yes | yes | PR #51 created with comprehensive body + test plan + review trail. |
| 14 — PR review | yes | yes | Primary-session R1 per cycle-36 L2. Skip R3 per cycle-17 L4 (≤25 ACs, no NEW security enforcement, ≤10 design Qs). APPROVE no blockers. |
| 15 — Merge + verify | yes | yes | `gh pr merge 51 --squash --delete-branch`. Post-merge CI green (run 24952323997, all step-level conclusions success). Late-arrival CVE check: same 4 baseline alerts. |
| 16 — Self-review + skill patch | in progress | — | This document. |

**Net:** 13/16 steps executed (Step 6 + Step 9.5 + Step 11.5 legitimately skipped per their skip-when conditions). All executed steps first-try. Two surprises both refine prior lessons (C35-L1 + C36-L3).

## Cycle-37 lessons → feature-dev skill patches

### L1 — Two-commit cycles when scope decomposes into independent areas

**Trigger:** Cycle 37 had two independent areas (security fix in `src/kb/review/context.py` vs requirements file split). Two-commit + 1-doc-commit sequence (3 commits total before push) was atomic per area, ONE CI run, ZERO failed CI runs visible to user — direct contrast to cycle-36's four-commit pattern (probe → fix → strict-gate → pivot) that produced 4 failed CI runs.

**Why it worked:** The cycle-36 four-commit pattern was driven by NEW CI dimension introduction (windows-latest matrix). Cycle 37 introduced ZERO new CI dimensions per cycle-36 L1. With no probe needed, local-verify-first + push-once is correct.

**Generalisable rule:**

> When the cycle's scope decomposes into N independent areas (security fix + tooling + docs) and there are zero new CI dimensions, batch each area as one commit, then push ONCE. Single CI run, zero user-visible CI failures during cycle work.
>
> Self-check at Step 7 plan: count "new CI dimension" items in the cycle. If zero AND scope is N independent areas: plan N commits + 1 doc-update commit, push once.

**Refines:** cycle-36 L1 (CI cost discipline). C36-L1 said "one new CI dimension per cycle"; C37-L1 says "ZERO new CI dimensions = single push, no probe needed."

**Skill-patch target:** `feature-dev` Step 7 plan section — add an explicit "CI run count" pre-check. If a cycle has zero new dimensions, default to single-push commit cadence.

### L2 — Additive over replacement when adding a new workflow alongside an existing artifact

**Trigger:** Cycle 37 design Q3 amendment. Original AC7 was "replace `requirements.txt` with a shim that includes all 6 new files". R1 design eval flagged that this would re-introduce version drift — the existing `requirements.txt` is a frozen 295-line snapshot for `pip install -r requirements.txt` reproducibility. Replacing it with a 6-line shim of `>=` specifiers means pip resolver picks LATEST versions on every install. Net: backward-compat-breaking change for marginal tidiness gain.

**Why the additive path won:** Both workflows can coexist. Existing snapshot remains the canonical reproducibility path; new files are opt-in for users who want lean installs (per-feature pip install). README documents both. Zero user-facing churn.

**Generalisable rule:**

> When the cycle adds a NEW workflow (per-extra requirements files, alternative CLI command, new MCP tool), default to ADDITIVE over REPLACEMENT to preserve backward compat on the existing artifact. The replacement-style "tidiness" gain is rarely worth the migration cost when the existing artifact is a long-lived contract that downstream users depend on.
>
> Self-check at Step 5 design gate: when an AC says "replace X with Y", ask: (a) is X a long-lived stable artifact (requirements.txt, CHANGELOG.md, public CLI command); (b) does the replacement break ANY existing user workflow? If both yes, route to AMEND with "additive instead of replacement".

**Refines:** cycle-36 L3 (post-pivot doc-accuracy fix) — both lessons share the principle that mid-cycle pivots and replacement-style ACs introduce "X used to mean Y but now means Z" drift. Additive avoids drift entirely.

**Skill-patch target:** `feature-dev` Step 5 decision gate — explicit "additive vs replacement" probe in the gate's Q-resolution section when an AC text begins with "replace".

### L3 — `pip-audit` JSON output prepends a status line; strip before parsing

**Trigger:** Step 2 pip-audit baseline capture: `pip-audit --format json > baseline.json` writes a leading line `Found N known vulnerabilities in M packages\n` BEFORE the JSON document. `json.loads(open(...).read())` fails with `JSONDecodeError: Expecting value: line 1 column 1`.

**Workaround:** `text[text.index('{'):]` strips the prefix. Surfaced again in Step 11 PR-CVE diff.

**Generalisable rule:**

> When piping `pip-audit --format json` to a file for later parsing, strip any leading status line: `text = open(path).read(); data = json.loads(text[text.index('{'):])`. Or invoke with `--quiet` if available (verify via `pip-audit --help`).
>
> Self-check at Step 2 baseline + Step 11 diff scripts: never `json.load(open(path))` directly on pip-audit output. Always strip the prefix first.

**Refines:** cycle-35 L1 (pip-audit binary invocation) and cycle-22 L1 (cve-baseline non-empty check). C37-L3 adds the parsing-nuance class to the established invocation discipline.

**Skill-patch target:** `feature-dev` Step 2 + Step 11 prompt sections — note the prefix-strip pattern as a one-liner.

### L4 — Skip R3 when triggers don't fire (positive validation, refines cycle-17 L4)

**Validated pattern:** Cycle 37 triggered NONE of cycle-17 L4's R3 conditions: 9 ACs (≤25), no new filesystem-write surface (existing `pair_page_with_sources` was already a write boundary; AC1 fixed an existing check, didn't add one), no NEW security enforcement point (AC1 fixed dead-code; existing `relative_to(raw_dir.resolve())` shape was correct, just on wrong control flow), 6 design questions (≤10). Skipped R3 — no audit-doc drift surfaced post-merge, no missed coverage. R1 primary-session caught all the architectural + edge-case concerns.

**Generalisable rule:** Continue running the cycle-17 L4 R3 trigger check at Step 14. If zero triggers fire AND R1 verdict is APPROVE with no blockers, skip R3. The cycle-37 evidence reinforces the trigger thresholds.

**Skill-patch target:** No new patch needed — cycle-17 L4 stands. Cycle 37 is a positive validation case worth citing in the SKILL.md index entry.

### L5 — Primary-session is the new default for small cycles (positive validation)

**Validated pattern:** Cycle 37 ran Steps 1-2-3-4-5-7-8-9-12-14-16 entirely primary-session. Subagent dispatches: zero. Total wall time from `/feature-dev` invocation to merge: ~50 min (vs cycle 36's ~3 hours of cumulative agent-wait time across multiple dispatches).

The user's "too many pause" feedback (saved to memory `feedback_minimize_subagent_pauses`) is the operational target. Cycle 37 hit it.

**Generalisable rule:**

> Primary-session is the DEFAULT for small-to-medium cycles (≤15 ACs, ≤5 src files, primary holds context from prior cycle). Subagent dispatch is reserved for: (a) genuine parallelism where two independent threads of inquiry can run concurrently (e.g., Step 4 R1 + R2 design eval over a 500-line spec); (b) tasks where the primary lacks context and reading the full prereq would blow the budget; (c) cycles ≥30 ACs where review fan-out justifies dispatch overhead.
>
> Self-check at every step boundary: ask "does primary already hold the context I need?" If yes, skip dispatch. Cycle-13 L2 already established this for Step 9 implementation; cycle-37 generalises it to Steps 1-2-3-4-5-7-8-12-14-16.

**Refines:** cycle-13 L2 (primary-session for small mechanical changes), cycle-36 L2 (tightly-scoped review goes primary), cycle-21 L1 (plan-gate REJECTs resolved inline). Cycle-37 elevates "primary-session by default" from a per-step heuristic to a cycle-level operating principle.

**Skill-patch target:** `feature-dev` skill preamble — add an "Execution mode" section near the top stating that primary-session is the default and listing the dispatch-warranted conditions.

## Cycle-38 candidates (filed at cycle-37 close — same 5 as cycle-36 BACKLOG)

Per cycle-23 L3 deferred-promise check, all 5 cycle-37 BACKLOG entries shifted to cycle-38+:
1. windows-latest CI matrix re-enable
2. GHA-Windows multiprocessing spawn investigation
3. mock_scan_llm POSIX reload-leak investigation
4. TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour
5. Dependabot pip-audit drift on 2 litellm GHSAs (monitor only — pip-audit doesn't surface)

Each entry retains its concrete fix-shape. No new deferred promises introduced by cycle 37.

## Summary

Cycle 37 shipped clean: 9 ACs, 3 commits, ZERO failed CI runs, ~50 min wall time, primary-session throughout, R3 skipped per trigger checks. Two production-touching changes (1 src security fix + tooling) plus tests + docs + BACKLOG cleanup. The "two-commit cycle" pattern (C37-L1) and "additive over replacement" principle (C37-L2) are the two new generalisable lessons; "primary-session by default" (C37-L5) is a positive validation worth elevating to a top-level skill principle.
