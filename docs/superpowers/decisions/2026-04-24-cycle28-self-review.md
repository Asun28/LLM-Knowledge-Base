# Cycle 28 — Self-review (Step 16)

**Date:** 2026-04-24
**Cycle:** 28
**Scope:** First-query observability (`VectorIndex._ensure_conn` + `BM25Index.__init__`) + BACKLOG hygiene + CHANGELOG commit-count rule codification + CVE re-verify.
**Outcome:** 9 AC / 7 commits / 2801 → 2809 tests. Merged as commit `433a93f`. Zero new CVEs.

## Scorecard

| Step | Executed? | First-try? | Notes |
|------|-----------|------------|-------|
| 1 — Requirements + ACs | yes | yes | Drafted in primary session; 9 ACs across observability + hygiene + CVE. |
| 2 — Threat model + CVE baseline | yes | yes | Opus subagent produced 8 threats T1-T8 + 6-candidate scope-out list in ~4 min. Baseline `.data/cycle-28/cve-baseline.json` matched cycle-26 exactly (2 CVEs, no upstream fix). |
| 3 — Brainstorming | yes | yes | Primary session; 3 approaches (precedent-mirror / unified module / context-manager); Approach A recommended. 8 open questions raised. |
| 4 — Design eval R1 + R2 parallel | yes | yes | R1 Opus APPROVE-WITH-CONDITIONS + 3 conditions, R2 Codex APPROVE-WITH-CONDITIONS + 3 conditions + Q9-Q11 additions. Both returned within ~4 min. |
| 5 — Decision gate | yes | yes | Opus resolved Q1-Q11, collapsed 6 conditions into 14 load-bearing C1-C14 per cycle-22 L5. Escalate empty. |
| 6 — Context7 | SKIP | N/A | Pure stdlib (time.perf_counter, logging, threading). Skip clause applied. |
| 7 — Plan | yes | yes | Primary session per cycle-14 L1 (operator held full context from Steps 1-5). 7 tasks, grep-backed Risk checklist. |
| 8 — Plan gate | yes | **no** | Codex REJECT with 9 gaps + 1 PLAN-AMENDS-DESIGN. Per cycle-21 L1, resolved ALL inline (7 gaps = doc-only / cosmetic; 2 gaps = real plan additions). Appended plan-gate-amendments section A1-A7. |
| 9 — Implementation | yes | yes | Primary per cycle-13 sizing heuristic (<30 LOC src + <100 LOC tests + stdlib-only). TDD: 8 failing tests written first, both src files instrumented, all 8 pass in 0.62s. |
| 10 — CI gate | yes | yes | Full-suite: 2800 passed + 9 skipped = 2809 (cycle-22 L3 full-suite discipline). Ruff clean post-autofix. |
| 11 — Security verify | yes | yes | Codex APPROVE-WITH-PARTIAL. All 8 threats IMPLEMENTED. 4 PARTIALs = grep-spec drift (cycle-12 L3 cosmetic); documented as such. |
| 11.5 — Existing-CVE patch | SKIP | N/A | diskcache + ragas both `fix_versions=[]` — no upstream patches available. Matches cycle-25/26/27 pattern. |
| 12 — Doc update | yes | yes | Done inline as commit 2 of the feat+docs pair (cycle-26 precedent). CLAUDE.md updated at both test-count sites (cycle-26 L2 discipline). |
| 13 — Branch finalise + PR | yes | yes | PR #42 opened with comprehensive review-trail body. |
| 14 — PR review R1 + R2 + R3 | yes | **no** | R1 Sonnet found 2 MAJORs (M1 C1 ordering + M2 test 5 vacuity) — fixed in `d9053c4`. R2 Codex APPROVE. R3 triggered per cycle-17 L4 (11 design-gate Qs ≥ 10 threshold); R3 Sonnet APPROVE + flagged 2 pre-existing uncommitted BACKLOG entries to commit pre-merge (`rebuild_indexes` audit status + override containment from prior R2/R3 sessions). |
| 15 — Merge + cleanup | yes | yes | Squash-merged `433a93f`. Branch auto-deleted via `--delete-branch`. Dependabot late-arrival diff: 1 alert (ragas, unchanged from cycle-27). |
| 16 — Self-review + skill patch | in progress | yes | This document. |

## What worked

1. **Cycle-26 precedent-mirror (Approach A) compressed design time.** Reviewers recognised the pattern from cycle 26's recently-merged PR #40; R1 Codex verdict was APPROVE-WITH-PARTIALS (no blockers) because the pattern was already validated. Zero time spent re-justifying the locked-vs-lock-free counter asymmetry.

2. **Real-elapsed test instrumentation over `time.perf_counter` monkeypatching.** Using `time.sleep(0.35)` inside a `sqlite_vec.load` stub exercised real wall-clock measurement. Zero raw `time.perf_counter = ...` assignments in the test file — C7 satisfied vacuously, and no leak risk across test boundaries.

3. **Plan-gate REJECT inline resolution (cycle-21 L1).** Codex's 9 gaps were 7 doc/grep-spec + 2 real additions. Resolving inline saved ~15 min vs re-dispatching Codex for a plan rewrite. Documented the resolution as an explicit "Plan-gate amendments" section (A1-A7) so future-me can see the reasoning.

4. **Security-verify PARTIAL triaging (cycle-12 L3).** All 4 PARTIALs were cosmetic grep-spec drift (docstring mentions of `time.perf_counter`, BRE-vs-ERE regex, comment-only `finally:`, format-guide vs Quick-Reference grep scope). Cycle-12 L3 gave me the vocabulary to flag them as cosmetic without looping Step 11 → Step 9.

5. **Pre-existing-uncommitted-work discovery at R3.** R3 Sonnet caught two previously uncommitted BACKLOG entries from prior sessions. Without R3's broader audit-doc-drift sweep, they would have vanished on `git branch -d`.

## What hurt

1. **C1 wording drift vs cycle-26 precedent.** My initial Step-9 implementation followed cycle-26's `_get_model` ordering (assignment → elapsed → counter → log), which R1 Sonnet flagged as M1 because the cycle-28 design doc's C1 explicitly said `elapsed` BEFORE `self._conn = conn`. The design wording was prescriptive; cycle-26 precedent was equivalent in measurement but different in literal ordering. **Lesson:** when a design CONDITION uses literal ordering words like "BEFORE / AFTER" on line-level code placement, honour them verbatim in Step 9 — don't defer to prior-cycle precedent. If the literal wording is unnecessarily tight, flag at Step 5 decision gate (not Step 9 implementation).

2. **Test 5 vacuity (R1 Sonnet M2).** Test 5 sampled counter BETWEEN two `_ensure_conn` calls and asserted delta == 0. Under a full counter-increment revert, delta was ALSO 0 → test passed vacuously. Cycle-11 L2 / cycle-16 L2 / cycle-24 L4 "revert-tolerant test" lessons all apply; I knew the pattern but didn't apply it to THIS test. **Lesson:** counter-stability tests MUST include an "increment did happen" pin. Pattern: `baseline = X(); trigger_increment(); assert X() - baseline == 1; trigger_expected_noop(); assert X() - baseline == 1`. The pre-trigger baseline is the revert-divergence anchor.

3. **Plan-gate ambiguity on doc-only AC test assertions.** Plan gate's first 3 REJECT gaps complained that AC7/AC8/AC9 have no "revert-failing test". But these are doc-only mutations (BACKLOG deletes, CHANGELOG comment line, CVE re-stamp) — adding production tests for them would violate cycle-11 L2 "inspect-source tests" anti-pattern. Spent ~5 min writing the A1 dismissal rationale. **Lesson:** Step 7 plan should explicitly note "no regression test — doc-only per cycle-26 AC7 precedent" on doc ACs so plan-gate Codex doesn't re-flag it.

4. **Pre-existing BACKLOG modification surprise.** Session started with `M BACKLOG.md` containing 2 `rebuild_indexes`-related MEDIUM entries from prior R2/R3 Codex sessions. I initially thought there was only 1 entry (the `audit status` one); R3 Sonnet found a 2nd entry (`hash_manifest/vector_db overrides`) that I missed. **Lesson:** when the session starts with uncommitted files, run `git diff <file>` early — not just `git status --short` — to inventory the full content. Critical when multiple prior sessions may have added disjoint content.

## Skill patches (feature-dev SKILL.md)

Three new lessons to append per cycle-16/17/26 precedent. All are refinements of existing skill content, not net-new sections.

### L1 — Design CONDITION literal ordering words are verbatim mandates (refines cycle-22 L5)

**Rule:** When a design-gate CONDITION uses literal ordering words ("BEFORE / AFTER") on line-level code placement, Step 9 MUST honour them VERBATIM — do not defer to prior-cycle precedent even when measurement is functionally equivalent. Why: the design gate is the contract; code reviewers (R1) will compare actual code vs design text, not vs prior precedent.

**How to apply:**
1. At Step 5: if the literal wording in a CONDITION is unnecessarily tight (e.g. the ordering doesn't affect semantics), flag as Q/DECIDE at the gate so the wording is either relaxed or intentional.
2. At Step 9: before writing the edit, cross-reference each "BEFORE / AFTER / INSIDE" phrase in the conditions against the target code — render them explicitly as inline comments (e.g. `# C1 — elapsed BEFORE self._conn`).
3. Self-check: grep the Step-9 diff for every CONDITION's literal ordering language; verify the code arrangement matches.

**Cycle 28 evidence:** R1 Sonnet M1 flagged `elapsed = time.perf_counter() - start` AFTER `self._conn = conn` as a C1 violation. Functionally equivalent (elapsed span identical), but the design text said BEFORE. Fix was a 1-line swap — cost of the fix was low, but the R1 → fix → R2 cycle added ~15 min. Adding the comment-level "# C1 — elapsed BEFORE self._conn" during initial Step 9 would have caught it during self-review.

### L2 — Counter-stability tests need a pre-trigger baseline anchor (generalises cycle-11 L2 + cycle-16 L2 + cycle-24 L4)

**Rule:** Tests of "counter stays constant under condition X" are revert-tolerant unless they ALSO pin "counter increment HAPPENED under condition Y". Pattern: capture baseline BEFORE the expected-increment trigger; assert delta after trigger; THEN trigger the expected-noop; assert delta unchanged. Under a full counter-increment revert, the FIRST delta check flips to fail — the test stops being vacuous.

**How to apply:**
1. When writing a regression test for a `+= 1` / counter-stable pattern, structure as `baseline → trigger_A → assert_A → trigger_B → assert_B_unchanged` (not `trigger_A → snapshot → trigger_B → assert_delta_zero`).
2. Self-check before commit: mentally revert the production increment; trace the test; confirm AT LEAST ONE assertion flips.
3. The pre-trigger baseline is the revert-divergence anchor — skipping it leaves the test passing under BOTH production and reverted code.

**Cycle 28 evidence:** `test_sqlite_vec_load_count_stable_on_fast_path` v1 sampled counter BETWEEN two `_ensure_conn` calls and asserted delta == 0. Under full revert of `_sqlite_vec_loads_seen += 1`, the counter stays at baseline — delta still 0. R1 Sonnet M2 caught it. v2 captures baseline BEFORE the first call, asserts after_first == 1 (flips under revert) AND asserts after_second == 1 (pins fast-path).

Generalises: cycle-11 L2 "source-scan tests are inspect.getsource in disguise", cycle-16 L2 "stdlib-helper-in-isolation tests don't catch reverts", cycle-24 L4 "content-presence assertions are revert-tolerant". Adds counter-stability tests to the same anti-pattern family.

### L3 — Inventory uncommitted files via `git diff` BEFORE the session inherits them (refines cycle-18 L1)

**Rule:** When the session starts with pre-existing uncommitted files, run `git diff <file>` on each to inventory the FULL content — not just `git status --short` for file names. Critical when multiple prior sessions may have added disjoint content (e.g. two different R2/R3 Codex reviews each appended a different BACKLOG entry).

**How to apply:**
1. Step 0 / session-start: for every `M` / `A` entry in `git status --short`, run `git diff <file>` (or `git diff --cached <file>` for staged) to see the full pre-existing delta.
2. If the content is cycle-scope-relevant, decide during Step 1 whether to roll it into the cycle or leave it for a separate commit.
3. At Step 15 (pre-merge), re-run the inventory — R3 Sonnet's audit-doc-drift sweep will catch gaps the primary misses.

**Cycle 28 evidence:** Session started with `M BACKLOG.md` containing TWO pre-existing MEDIUM entries (`rebuild_indexes audit status` R2 Codex + `rebuild_indexes hash_manifest/vector_db overrides` R3 Codex). My initial `git diff` reading surfaced only the first; I described the pre-existing modification as "one entry" to R3. R3 Sonnet's audit caught the second entry that I missed and flagged commit-before-merge to avoid branch-cleanup loss. Without R3, the second entry would have vanished.

Same class as cycle-18 L1 (snapshot-bind on `PROJECT_ROOT`) — both are "what's already in scope that I didn't notice" classes.

## Final counts

- **AC:** 9
- **CONDITIONS:** 14 (14/14 grep-verified or documented-as-cosmetic)
- **Threats:** 8 (8/8 IMPLEMENTED per Step-11 security verify)
- **Commits:** 7 on branch (feat + 3 docs + fix + R2-doc + R3-doc+BACKLOG-adds); matches CHANGELOG
- **Tests:** 2801 → 2809 (+8)
- **CVEs:** baseline 2 → branch 2 (no change); INTRODUCED=[], REMOVED=[]
- **Review gates:** R1 Codex APPROVE-WITH-PARTIALS + R1 Sonnet APPROVE-WITH-NITS + R2 Codex APPROVE + R3 Sonnet APPROVE
- **Merge:** `433a93f` on main
- **Duration:** ~2 hours end-to-end (Step 1 start ~18:07 → Step 15 merge ~19:25)
