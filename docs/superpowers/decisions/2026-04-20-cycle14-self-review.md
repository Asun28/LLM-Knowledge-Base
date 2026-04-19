# Cycle 14 — Step 16 Self-Review

**Date:** 2026-04-20
**Merge commit:** `67e3e12`
**Branch:** `feat/backlog-by-file-cycle14` (deleted post-merge)

## Scorecard

| Step | Executed? | First-try? | Surprises |
|------|-----------|------------|-----------|
| 1. Requirements + AC | yes | yes | initial AC count was 24; shrank to 21 at Step 5 after grep confirmed AC13/14/15 were duplicates of existing `detect_source_type` |
| 2. Threat model + CVE baseline | yes | yes | subagent surfaced 10 items T1-T10 with 6 AC amendments needed; pip-audit baseline 1 vuln (diskcache, pre-existing) |
| 3. Brainstorm | yes | yes | picked Approach A (big batch) per user ask for 30+ items; recorded as decision doc |
| 4. Design eval (R1 Opus + R2 Codex parallel) | yes | yes | both returned APPROVE WITH AMENDMENTS with overlapping findings; R1 Opus caught AC14 duplicate before primary grep |
| 5. Decision gate | yes | yes | resolved Q1-Q20 in primary session per auto-approve feedback; dropped 3 ACs |
| 6. Context7 verification | skipped | n/a | pure stdlib + python-frontmatter (already used extensively); quick local verification of `sort_keys=False` behavior instead |
| 7. Implementation plan | yes | yes | primary-session draft (cycle-13 L2 heuristic — faster than Codex dispatch for this context-rich plan) |
| 8. Plan gate | yes | yes | Codex returned AMEND-WITH-NOTES; 5 amendments folded inline (T7 N/A mapping, IDN/bare-domain tests, validate_frontmatter gating, cluster rationales, primary-session exception rationale) |
| 9. Implementation (7 tasks TDD) | yes | mostly | TASK 6 test `test_mature_with_missing_title_no_boost` initially wrong (empty title is actually valid per existing `validate_frontmatter`); replaced with empty-sources-list case. TASK 7 CLI tests initially failed due to out-dir containment check; fixed by pre-creating the dir. |
| 10. CI gate | yes | yes | one regression in `test_utils.py::test_load_all_pages_returns_all_fields` from additive `status` key → updated to include it |
| 11. Security verify + CVE diff | yes | mostly | Codex returned PARTIAL with 3 grep-contract deviations (T1 traversal string, T3 f-string in disambiguatingDescription, T10 sort_keys in comments); all fixed in-cycle before Step 12 |
| 11.5. Existing-CVE opportunistic patch | skipped | n/a | 0 Class A alerts in baseline; diskcache CVE has no fix available |
| 12. Doc update | yes | yes | CHANGELOG + BACKLOG + CLAUDE.md updated in one commit per convention |
| 13. Branch finalise + PR | yes | yes | PR #28 opened with full review trail body |
| 14. PR review (2 rounds) | yes | mostly | R1 Codex APPROVE (no majors); R1 Sonnet REQUEST-CHANGES with 2 MAJORs + 4 minors. R1 Sonnet caught a legit fragile-pattern regression (`idx += 1` mutation inside enumerate) and a perf smell (double disk I/O per publish page). Both fixed in commit `cc18049`. R2 Codex re-review APPROVE. |
| 15. Merge + cleanup + late-CVE warn | yes | yes | merge commit 67e3e12; 0 late-arrival alerts |
| 16. Self-review + skill patch | yes (this doc) | — | — |

## Stats

- 21 ACs shipped across 9 source files + 1 new module (`src/kb/compile/publish.py`)
- 13 commits total (11 feature + 1 R1 fix + 1 merge)
- Tests: 2140 baseline → 2238 final (+98 net; 8 new test files)
- No dependency changes; 0 PR-introduced CVEs
- 0 Dependabot alerts open pre-merge; 0 late-arrival alerts post-merge
- 4-round review trail: R1 parallel (Codex + Sonnet), R1 fixes, R2 Codex verify

## Lessons

### L1 — Primary-session implementation plan draft beats Codex dispatch for context-rich plans

**Observation:** Per cycle-13 L2 "primary-session sizing heuristic", I wrote the Step 7 implementation plan in the primary session rather than dispatching Codex. The plan itself was ~170 lines, and the primary session already held full context (requirements + threat model + design-gate decisions + grep evidence for every symbol). Codex dispatch would have required re-delivering that context verbatim in the prompt. Time-wise: primary took ~5 minutes; Codex dispatch typically takes 5-15 minutes polling + a context-delivery prompt. The plan-gate (Step 8) then caught the 5 amendments regardless, which is the proper separation of concerns.

**Rule:** Step 7 plan drafting is a primary-session task when the cycle has >15 ACs and the operator already holds the context. Codex plan drafting is correct when the operator has LESS context than the plan requires (e.g., brand new module in an area the primary session hasn't explored). Document this in the Step 7 block of the skill.

### L2 — `enumerate` loop-variable mutation is a code-review BLOCKER class

**Observation:** In `publish.py::build_llms_full_txt`, my initial implementation contained `idx += 1` inside a `for idx, page in enumerate(kept):` block to shift the "written pages" counter after an oversized-first-page branch. R1 Sonnet correctly flagged this as "a correctness coincidence" — the arithmetic happened to be right for idx=0 but would silently break if someone moved the check to a non-first index. The code passed my initial self-review because the oversized-first-page test path was the only branch exercised.

The core risk: mutating a loop-control variable inside a Python `for` loop that uses `enumerate` doesn't affect iteration (enumerate's counter is independent). Readers who aren't attentive to this distinction can misinterpret the intent, and linters don't catch it.

**Rule:** Add a Red Flag row to Step 9 / Step 14 checks: "reassigning the unpacked variable from `enumerate(...)` inside the loop body". When writing any counter-tracking logic inside an `enumerate` loop, use a separate named variable (e.g., `pages_written = 0` updated explicitly) rather than mutating `idx`.

### L3 — Additive fields in `load_all_pages` should ship all at once, not piecemeal

**Observation:** My cycle-14 TASK 6 added `status` to `load_all_pages`. My cycle-14 TASK 7 then built publish filters that needed `belief_state` AND `confidence`. I shipped publish with a slow-path that opened `frontmatter.load(page_path)` per page for each builder, because `belief_state` wasn't in `load_all_pages`. R1 Sonnet correctly flagged the double disk I/O. The fix was trivial: add `belief_state` + `authored_by` as additive keys alongside `status`. Had I added all three at once in TASK 6, TASK 7 would have been correct by construction.

**Rule:** When a cycle introduces a new metadata vocabulary (cycle 14 added `belief_state` / `authored_by` / `status` together per AC1), surface ALL of them in `load_all_pages` together as part of the AC, not one-at-a-time driven by individual consumer needs. The vocabulary arrival should trigger loader-extension in the same cycle.

## Skill patches

Three patches land in `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md`:

### Patch 1 — Step 7 primary-session plan-drafting heuristic

New subsection under Step 7 block:

> **Primary-session plan draft heuristic (added 2026-04-20, cycle-14 L1).** Draft the implementation plan in the PRIMARY session when: (a) the cycle has ≥ 15 ACs, (b) the operator already holds full context from Steps 1-5 (requirements + threat model + design-gate decisions), and (c) the plan needs to reference specific code locations the operator has already grep-verified. Codex dispatch adds ~10 minutes of polling + a context-delivery prompt round-trip; when the primary already has the context, writing the plan directly is faster. The Step 8 plan-gate still runs regardless — it's the quality check, not the plan-drafting. Reserve Codex dispatch for Step 7 when the operator has LESS context than the plan requires (new module in unexplored territory, tasks dependent on code the operator hasn't read).

### Patch 2 — Red Flag for enumerate-loop variable mutation

New row in Red Flags table:

> | "I'll just `idx += 1` inside the `for idx, x in enumerate(...)` loop to shift a counter" | **Loop-variable mutation inside `enumerate` is a silent correctness bug.** `enumerate` drives `idx` from its own internal counter; your in-body assignment doesn't affect iteration and is likely a no-op or relies on coincidental arithmetic. Replace with a separate named counter variable (e.g., `pages_written = 0` updated explicitly inside the loop and referenced after the loop). Lesson from 2026-04-20 cycle 14 R1 Sonnet MAJOR 1: `build_llms_full_txt` used `idx += 1` before computing `truncated_count = len(kept) - idx` — the arithmetic happened to be correct for `idx=0` but would silently break if the oversized-page branch ever fired at `idx != 0`. Fix: explicit `pages_written` variable tracked through every branch that advances the written count. |

### Patch 3 — Step 9 rule for metadata-vocabulary-shipping

New note under Step 9 subagent-driven development subsection:

> **Loader-side additive fields ship together (added 2026-04-20, cycle-14 L3).** When the cycle introduces a new metadata vocabulary (e.g., three frontmatter fields in one AC), surface ALL of them in `load_all_pages` or the equivalent loader in the SAME task. Shipping them piecemeal — "this consumer needs field A, next consumer needs field B" — forces the second consumer onto a slow-path (e.g., re-opening `frontmatter.load` per page bypassing the cache). Rule: the AC that lands the vocabulary should also land the loader-additive keys. Per cycle 14 TASK 6/7: `status` landed in TASK 6 for ranking; `belief_state`/`authored_by` had to be retrofitted when TASK 7 publish needed them. R1 Sonnet caught the double disk I/O; a same-cycle loader-extension would have prevented the regression.
