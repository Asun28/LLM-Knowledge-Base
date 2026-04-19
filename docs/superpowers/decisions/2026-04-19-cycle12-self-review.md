# Cycle 12 — Step 16 Self-Review + Skill Patch

**Date:** 2026-04-19
**Merged:** PR #26 at commit `c228a30` (16 commits ahead of main pre-merge; `a5416b3` → `c228a30`).
**Shipping:** 17 ACs / 13 files / 13 commits / 2089 → 2119 tests (+30). 0 open Dependabot alerts post-merge.

## 16-step scorecard

| # | Step | Executed? | First-try? | Surprise / iteration detail |
|---|------|-----------|------------|-----------------------------|
| 1 | Requirements + AC list | yes | yes | 17 ACs in one pass, mapped 1:1 to BACKLOG entries + 1 deferred-test pin |
| 2 | Threat model + CVE baseline | yes | yes | Opus returned PASS-WITH-NOTES + 4 action items; `pip-audit -r requirements.txt` failed on ResolutionImpossible, but `pip-audit` (venv-installed) succeeded — recorded the alternate path in CVE baseline doc |
| 3 | Brainstorming | yes | yes | Selected Approach B (cluster-by-logical-unit) with 5 open Qs |
| 4 | Design eval R1+R2 (parallel) | yes | yes | Opus R1 PASS-WITH-NOTES + Codex R2 PASS-WITH-CHANGES; R2 surfaced 7 material issues beyond R1 (including AC9 function-name drift, AC8 LRU cache stream-through math, AC13 `raw_dir` not auto-derived) |
| 5 | Decision gate | yes | yes | Resolved 16 questions (5 brainstorm + 4 Opus-new + 7 Codex-new). All HIGH/MED-HIGH confidence; zero escalations |
| 6 | Context7 verification | SKIP | n/a | Clean skip — no new external library use (stdlib + existing internal helpers only) |
| 7 | Implementation plan | yes | yes | Codex produced 10-task plan with PRE-TASK-0 grep verification block; all file/line refs confirmed against source |
| 8 | Plan gate | yes | yes | APPROVE on first pass — every AC mapped to a TASK, every threat-model item + condition covered, dependency ordering correct |
| 9 | TDD implementation | yes | **1 TASK required manual completion** | TASK 9 (`codex:codex-rescue` for AC14 sanitizer pin) returned a "dispatched-and-polling" meta-response without an actual commit SHA. Implemented directly in primary session: wrote `test_cycle12_sanitize_context.py`, discovered U+200E/U+200F are deliberately preserved (cycle-3 R2 i18n scope), corrected the test, 3/3 green. Commit `6b6d5d8`. |
| 10 | CI hard gate | yes | yes | 2108 passed + 7 skipped in 385 s; ruff check + format-check both clean |
| 11 | Security verify + CVE diff | yes | **PASS-WITH-PARTIAL → follow-up** | Codex returned PASS-WITH-PARTIAL: AC2 `sweep_orphan_tmp` raised `FileNotFoundError` instead of never-raising; AC8 `load_page_frontmatter` shipped without the mtime docstring. Closed both in commit `36f74f2` with 3 regression tests; final state PASS. Class-B CVE diff empty (`requirements.txt` unchanged). |
| 11.5 | Existing-CVE patch | SKIP | n/a | Only open advisory is diskcache CVE-2025-69872 with no patched upstream release; already documented + mitigated in BACKLOG. No-op per Step-11.5 contract |
| 12 | Doc update | yes | yes | Shipped as TASK 10 in Step 9 (docs-last convention: BACKLOG sweep + CHANGELOG cycle-12 entry + CLAUDE.md `KB_PROJECT_ROOT` line). CHANGELOG refresh commit `ae18d00` after security-verify fix updated test count + commit count. |
| 13 | Branch finalise + PR | yes | yes | PR #26 opened cleanly with complete design-trail links + test plan |
| 14 | PR review R1+R2 | yes | **Codex CLI unavailable — Sonnet fallback for both R1 architect and R2** | R1 Codex returned "Codex CLI not installed" error; dispatched `everything-claude-code:architect` as Sonnet fallback. R1 architect APPROVE + 2 MAJORs (allowlist scope, sys.modules scope); R1 edge-case WARNING + 2 MAJORs (one already addressed per architect, one new). Fixed 3 majors in commit `0887ba1`. R2 Sonnet fallback APPROVE on first pass. |
| 15 | Merge + cleanup + late-arrival CVE | yes | yes | `gh pr merge --merge` at `c228a30`; local branch deleted; post-merge Dependabot alerts still `[]` (zero late-arrival CVEs) |
| 16 | Self-review + skill patch | yes (this doc) | — | — |

## Surprises → lessons

### L1 — Codex CLI unavailability at Step 14 R1 requires explicit fallback path

**What happened.** Dispatched `codex:codex-rescue` for R1 architecture review (a01c6ef2013c13763). Agent returned `"Codex CLI is not installed or its runtime support is missing. The codex-companion.mjs script requires @openai/codex to be installed globally."` Had to re-dispatch via `everything-claude-code:architect` Sonnet fallback.

**Why it matters.** The feature-dev skill documents "Codex unavailable → Sonnet fallback" inside Step 9 (`Codex unavailable → Skill("superpowers:subagent-driven-development") with Sonnet`) but NOT inside Step 14 (which currently says only "Codex+Sonnet, then Codex"). A fresh operator reading Step 14 wouldn't know to pre-emptively fall back.

**Skill patch (Step 14 section):** Add an explicit "Codex unavailable → Sonnet fallback" clause mirroring Step 9's rule, plus concrete subagent suggestions:
- R1 architecture role: `everything-claude-code:architect`
- R1 edge-case/security role: `everything-claude-code:code-reviewer`
- R2: either of the above; same reviewer is fine since fixes are the focus, not parallelism

### L2 — Codex dispatch with "polling pattern" summary ≠ completed work

**What happened.** TASK 9 Codex dispatch returned a summary beginning with `"Codex task dispatched (ID b8vbtnzhq). A background poller (b3es724nh) is watching for the output to become non-empty and will notify when done."` The summary then described EXPECTED results ("expect: commit X, test count Y, ...") rather than ACTUAL results. When I checked, NO commit was created and the test file did not exist. Had to implement TASK 9 manually in ~3 minutes.

**Why it matters.** A codex:codex-rescue agent that describes the intended outcome instead of returning concrete commit SHAs + test deltas has effectively failed. The trap: the summary reads like success ("Codex task dispatched", "once it completes expect..."). A less careful operator would mark the task done and move to the next one, shipping partial work.

**Skill patch (Step 9 section):** Add a Red Flag row: when a `codex:codex-rescue` summary mentions "dispatched", "polling", or "will notify" WITHOUT providing (a) a concrete commit SHA and (b) actual test-count delta, treat as FAILED dispatch. Re-dispatch once, then fall back to manual implementation in the primary session.

### L3 — Step 11 PARTIAL gaps should close in-cycle via a follow-up commit, not defer

**What happened.** Step 11 security verify returned PASS-WITH-PARTIAL: two minor contract gaps (`sweep_orphan_tmp` raising vs never-raising; `load_page_frontmatter` missing mtime docstring caveat). Both were easy to close in ~10 minutes. The skill says "PARTIAL <gap>" without prescribing what to do next — a naive read could defer to BACKLOG.

**Why it matters.** PARTIAL gaps are by definition the design contract minus some subset. Deferring them means merging a PR that knowingly ships a contract-deviation. Rule: if the gap is a contract-deviation on an AC that's in this cycle's scope, close it in a follow-up commit before Step 13. Don't punt to cycle N+1 unless the fix itself needs its own design pass.

**Skill patch (Step 11 section):** Add explicit "PARTIAL handling" paragraph — distinguish (a) contract-deviation on in-scope AC (close in-cycle via follow-up commit + regression test before Step 13), (b) out-of-scope follow-up (BACKLOG entry OK).

## Other notes

- **R1 parallelism paid off.** Architect and edge-case reviewers surfaced COMPLEMENTARY findings. Architect caught scope (allowlist, sys.modules). Edge-case caught test robustness (negative test gap, snapshot brittleness). Neither would have found all 4 alone.
- **The `codex:codex-rescue` dispatch footgun** (the 2026-04-17 `pytest`-as-model misparse) did NOT recur this cycle — the prompt wrapping discipline is paying off.
- **User memory `feedback_batch_by_file`** held up well for 17 ACs across 13 files. Approach B (cluster commits) was the right call; per-file strict would have split AC7 cluster across 3 broken-intermediate commits.
- **Design gate Q9** (walk-up bound = 5 levels) was arbitrary at time of decision. Cycle 12 didn't exercise depth 4+ in any test. Consider lowering to 3 in a future hygiene cycle OR writing a test that covers depth-5 to validate the rationale.

## Cycle stats

- **Commits on branch:** 13 (10 TDD + 1 security-verify fix + 1 R1 fixes + 1 CHANGELOG refresh).
- **Tests:** 2089 → 2119 (+30). Full suite 2112 passed + 7 skipped.
- **Files touched (src):** `config.py`, `mcp_server.py`, `mcp/__init__.py`, `utils/io.py`, `utils/pages.py`, `lint/checks.py`, `graph/builder.py` (7).
- **Files touched (tests):** `conftest.py` + 5 new `test_cycle12_*.py` + `test_v5_lint_augment_cli.py` + `test_v5_lint_augment_orchestrator.py` (8).
- **Files touched (docs):** `BACKLOG.md`, `CHANGELOG.md`, `CLAUDE.md` + 6 decision docs (9).
- **Blast radius per design-gate:** exactly 13 production/test files + docs — matches Step 1 prediction.
- **Class-B CVE introduced:** 0.
- **Class-A CVE patched:** 0 (only advisory is unfixable; already mitigated).
- **Dependabot alerts post-merge:** 0.

## Conclusion

Cycle 12 shipped cleanly. Three documented lessons for `feature-dev` SKILL.md:

1. Step 14 needs an explicit "Codex unavailable → Sonnet fallback" subsection mirroring Step 9.
2. Step 9 Red Flags needs a "Codex polling-pattern summary ≠ done" row.
3. Step 11 needs explicit PARTIAL-handling guidance (close in-cycle vs BACKLOG).

Skill patches in the companion commit.
