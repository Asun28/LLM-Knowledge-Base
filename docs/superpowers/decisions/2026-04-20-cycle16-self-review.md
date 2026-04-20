# Cycle 16 — Step 16 Self-Review

**Date:** 2026-04-20
**Scope:** 24 ACs across 8 source files + 9 new test files. 14 commits. Tests 2334 → 2464 collected (+130). PR #30 merged (94cac26 on main).
**Dependabot:** 0 open alerts pre-cycle, 0 open post-merge (late-CVE check clean).

---

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | yes | — 15 threats; Opus subagent delivered with complete Step-11 checklist in 189s. |
| 3 — Brainstorming | yes | yes | — selected Approach A (batch-by-file) matching `feedback_batch_by_file`. |
| 4 — Design eval (R1 Opus + R2 Codex, parallel) | yes | no | R2 Codex REJECT flagged 2 BLOCKs R1 Opus missed: AC18 `source: []` violates `validate_frontmatter` at `models/frontmatter.py:48` ("Source list is empty"); AC22 incremental-skip leaks retracted siblings. Both correct. Dual-reviewer pattern saved an implementation round. |
| 5 — Design gate (Opus) | yes | yes | 10 questions resolved to 10 options (9 decisive + 1 "drop dead code"); 6 conditions C1-C6 baked in. Zero ESCALATE. Q4 preserved AC4 text ("sort LAST") after R2 correctly read design as excluding absent-status — editorial not architectural. |
| 6 — Context7 verification | skipped | n/a | Pure stdlib/internal code (`re`, `xml.etree.ElementTree`, `json`). |
| 7 — Implementation plan | yes | yes | Primary-session drafted per cycle-14 L1 heuristic (24 ACs + operator held full Steps 1-5 context). Plan committed as artifact. |
| 8 — Plan gate (Codex) | yes | no | REJECT with 4 gaps: AC6 priority-sequence inline text, AC10 slug-form test, T4 fence test, T14 subdir-retained test. All 4 were test-assertion gaps, not plan-structure bugs. Amendments applied in-place; re-gate APPROVEd. |
| 9 — Implementation (TDD) | yes | mostly | 8 tasks shipped one-commit-per-file. TASK 2 had a cosmetic ruff issue (unused `priority_index` variable after deduplication — caught by ruff, fixed inline). TASK 4 had a `test_distance_0_excluded` expectation mismatch (I assumed distance=3 but the actual Levenshtein was ≥7 because `concepts/` vs `entities/` differs by 7+ chars) — test rewritten to match reality. |
| 10 — CI hard gate | yes | no | 2 pre-existing tests broke: `test_cycle14_coverage_gate.py::test_gate_triggers_refusal` asserted `call_llm never fires on refusal`; cycle 16 adds scan-tier rephrasings on that same path. `test_lint.py::test_run_all_checks` pinned `checks_run` count to 10; cycle 16 wired 2 more. Both updated in the same commit that closes the cycle — no CI regression. |
| 11 — Security verify + CVE diff | yes | no | Codex flagged HIGH N1: `_is_contained` used `str.startswith`. Fixed same-cycle per cycle-12 L3 (PARTIAL on in-scope AC = close IN-CYCLE, not BACKLOG). This turned out to be foreshadowing — R1 Sonnet caught the SAME bug at `_save_synthesis` a round later (different site, same class). Step 11 only caught one of two. See L1 below. |
| 11.5 — Existing-CVE patch | skipped | n/a | Dependabot 0 open alerts; pre-existing `diskcache` CVE remains unpatched upstream (informational). |
| 12 — Doc update | yes | yes | CHANGELOG + BACKLOG + CLAUDE.md in one pass; re-verified test count at Step 10 boundary, then re-synced after R1, R2, R3 fix commits. |
| 13 — Branch finalise + PR | yes | yes | PR #30 opened with full review trail. |
| 14 — PR review (3 rounds) | yes | no | Each round uncovered new findings: R1 (1 Blocker + 3 Majors + 2 Minors), R2 (3 test-vacuity issues on MY regression tests — cycle-11 L2 self-inflicted), R3 (2 NITs — one doc drift + one MCP surface gap). Every round was additive, not re-work. Three-round pattern justified. |
| 15 — Merge + cleanup | yes | yes | Merge commit `94cac26` on main. Feature branch deleted. Late-CVE check clean. |
| 16 — Self-review + skill patch | yes | yes | This document. |

---

## Lessons extracted (4 skill patches)

### L1 — Same-class peer scan MUST include `_save_synthesis` / MCP-write sites when a `_is_contained` fix lands

**What happened.** Step 11 Codex security verify correctly caught the N1 `_is_contained` `str.startswith` bug at `src/kb/compile/publish.py:386` and proposed the `Path.is_relative_to` fix — landed in commit `4201a1f`. The fix had a peer leak: `_save_synthesis` in `src/kb/mcp/core.py:160` used the SAME `str(resolved_target).startswith(str(resolved_base))` pattern. Step 11's same-class peer scan missed it because the scan prompt was scoped to "publish.py path containment" rather than "all path-containment sites in the diff". R1 Sonnet caught it at round 14 instead. Cycle-12 L3 PARTIAL handling rule held — both were fixed in-cycle — but at an extra review-round cost.

**Why it matters.** Future cycles that introduce a path-containment fix at site A should grep the entire diff for the SAME anti-pattern (`str.startswith(str(...))`, `startswith(str(base))`, `.startswith("/")` on resolved paths, etc.) BEFORE declaring the fix complete. Scan should be bounded to the CYCLE's diff (not the whole codebase) to stay affordable.

**Skill patch.** Amend Step 11 security verify prompt: "For any same-cycle fix that changes `Path.resolve` / containment / traversal logic, grep the ENTIRE `git diff origin/main` output for semantically identical anti-patterns at sites NOT explicitly in the threat-model item's enforcement list. Specifically: `str.startswith(str(` / `startswith(str(` / `.startswith(str(Path`. List every match; confirm each either uses the safe helper (`Path.is_relative_to`, dedicated `_is_contained`) or is explicitly justified (UNC-prefix check, protocol-scheme check, etc.)."

### L2 — Regression tests that assert helper semantics in ISOLATION don't catch production reverts

**What happened.** R1 Blocker 1 fixed `_save_synthesis` to use `Path.is_relative_to`. The regression test I wrote (`test_containment_check_rejects_sibling_prefix_dir`) asserted `malicious_target.is_relative_to(synthesis_dir)` — i.e. it exercised `Path.is_relative_to` directly, NOT `_save_synthesis`. Reverting `_save_synthesis` to `str.startswith` would NOT have failed the test. R2 Codex correctly identified this as cycle-11 L2 style vacuity. R1 Sonnet Major 3's regression had the same shape: it advanced the page mtime (which old AND new logic would both react to), not the dir mtime (which only old logic would react to incorrectly). The test didn't differentiate.

**Why it matters.** "Non-vacuous" doesn't only mean "uses production symbol imports + tmp fixtures" (the cycle-11 L2 lesson). It ALSO means "the production code path under test receives inputs that exercise the FIX site, not a helper that shares the fix". For fixes landing in a DEFENSIVE check (like `_save_synthesis`'s belt-and-suspenders containment), the test must stage the exact input-resolution pattern that reaches the defensive check — e.g. via `Path.resolve` monkey-patch, symlink, or a contrived `WIKI_DIR` where upstream validators can't prevent the condition.

**Skill patch.** Amend Step 9 Red Flag table to generalise cycle-11 L2: "Any regression test whose assertions invoke a stdlib helper (`Path.is_relative_to`, `shutil.move`, `json.loads`) directly — rather than through the production function that uses that helper — is a test-vacuity pattern EVEN IF the test passes the 'no inspect.getsource' sniff. The test must reach the production call site with inputs that diverge the two behaviours under comparison. Self-check before commit: for every regression test, ask 'if I replace my production fix with an OBVIOUSLY-broken alternative (e.g. `lambda *a: True`), does this test fail?' If no, the test is vacuous."

### L3 — Phantom-failure-mode fixes produce vacuous tests. Name them as readability, not security.

**What happened.** R1 Sonnet Minor 5 claimed `.format(question=q, ...)` would KeyError on literal `{` / `}` in the question. I applied a defensive concat-based refactor AND wrote a test (`test_question_with_braces_does_not_raise`) to regress it. R2 Codex correctly pointed out that `str.format` does NOT re-parse braces inside named-kwarg replacement values — so the test was a no-op in BOTH directions, and the fix was defensive against a failure mode that doesn't exist. I kept the refactor (it's cleaner) but dropped the test and rewrote the code comment to acknowledge the phantom.

**Why it matters.** When a reviewer proposes a defensive fix for a suspected failure mode, the author should mentally reproduce the failure BEFORE writing a regression test. If the failure can't be reproduced in a unit test — because the underlying API doesn't actually fail in the way claimed — the fix is a readability/style change, NOT a security/correctness fix. Labeling it the latter pollutes future audits and misleads reviewers.

**Skill patch.** Amend Step 14 R1 review response flow: "Before writing a regression test for a reviewer-proposed fix, reproduce the failure mode in a Python REPL or scratch `.py` file. If the failure mode can't be reproduced under the claimed inputs, the fix is not actually closing a regression — label the change as readability / hygiene in the commit message, skip the regression test, and add a code comment acknowledging the finding without claiming a fix. This prevents future audits from inheriting a phantom-failure-mode test + code claim."

### L4 — Four-round review cycle is worth it on a 24-AC batch even at the 25-threshold boundary

**What happened.** `feedback_3_round_pr_review` triggers at >25 items. Cycle 16 shipped 24 ACs — technically below the threshold — but I ran 3 rounds anyway on the theory that "close to threshold + complex path-containment + new MCP write surface" warranted the extra round. R1 flagged 6 items. R2 caught test vacuity in 3 of my R1-fix regressions (self-inflicted). R3 flagged 2 NITs including one real MCP surface gap (rephrasings swallowed by response builder). Each round produced distinct, actionable signal — no round was empty noise.

**Why it matters.** The 25-threshold is a heuristic, not a ceiling. The actual predictor of "worth 3 rounds" is the cycle's RISK PROFILE: new security surface (path traversal, prompt injection), new filesystem writes, new threat-model items. A 10-AC cycle adding a security-critical surface might warrant 3 rounds; a 40-AC cycle of pure test additions might not.

**Skill patch.** Amend `feedback_3_round_pr_review` guidance in feature-dev skill: "The 25-AC threshold triggers R3. Additionally, R3 is RECOMMENDED at >=15 ACs when ANY of: (a) a new filesystem-write surface is introduced (e.g. `kb_query(save_as=...)`), (b) a threat-model item lands with a defensive check whose exact input-resolution pattern is hard to reach from user input (high risk of vacuous-test regressions per L2), (c) the cycle introduces a NEW security enforcement point (slug validator, HTML escaper, XML builder, path-containment helper). Mark the rationale in the PR review-trail comment so auditors see why R3 fired below threshold."

---

## Completed

- PR #30 merged (`94cac26` on main) with 24 ACs shipped.
- **Dropped at design gate:** 0 — all 24 ACs from Step 1 passed through decision gates into production.
- Tests: 2334 → **2464 collected** (+130); **2457 passed + 7 skipped** runtime.
- Class B CVE diff: empty. Class A Dependabot: 0 open.
- All 15 threats IMPLEMENTED post-R1/R2/R3 fixes.
- Three-round review trail posted as PR comment; audit-ready.

## Next steps

Cycle 16 complete. User should run `/clear` before starting cycle 17 so the next design-eval runs against fresh context — stale AC numbers and R1/R2/R3 subagent IDs would otherwise pollute the next Step 4 pass.

Candidate cycle-17 scopes: (a) compile auto-hook for publish (BACKLOG item), (b) refactor to resolve the two open cycle-16 follow-ups, or (c) tackle Phase 4.5 HIGH architectural items still deferred (`kb.errors` hierarchy, `compile_wiki` rename, `refine_page` two-phase audit).
