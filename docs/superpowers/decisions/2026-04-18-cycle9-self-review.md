# Cycle 9 Step 16 Self-Review (2026-04-18)

**PR:** #23 merged at `dc9f7a5` (2026-04-18T09:10:13Z)
**Branch:** `feat/backlog-by-file-cycle9` (deleted)
**Scope:** 30 AC across 14 files + 2 security-review fixes + 1 bearer-split + 2 R1 fixes
**Final commits on main:** 21 cycle-9 commits + 1 merge commit
**Tests:** 1959 baseline → 1999 passing + 5 skipped (2004 collected); 40 new tests
**CVE:** 0 new; 0 Dependabot alerts at merge; pre-existing `diskcache` CVE-2025-69872 unchanged

## Step Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements | yes | no | User corrected `.env.example` "Required" → "Optional" mid-requirements; added AC31 and saved persistent memory `feedback_env_example_api_key_optional`. |
| 2 Threat model + CVE baseline | yes | yes | Clean — 0 Dependabot alerts; same `diskcache` Class A as cycle 8. |
| 3 Brainstorming | yes | yes | Batch-by-file with risk-weighted ordering was obvious per `feedback_batch_by_file` memory. |
| 4 Design eval (R1 Opus + R2 Codex) | yes | no | Codex R2 REJECT caught 3 SHIPPED items (AC9 kb_read_page ambiguity, AC15 `_check_rate_limit` docstring, AC26 cli fast-path) + 1 fixture target mismatch (AC22 `is_relative_to(PROJECT_ROOT)` vs `tmp_project`). Saved ~1 cycle of wasted implementation. |
| 5 Decision gate | yes | yes | 10 Q resolved; dropped AC9/AC26; added AC25 (MAX_PROMPT_CHARS guard); amended AC14 (debug log); retargeted AC28 (no new signature). |
| 6 Context7 | skipped — correct | yes | Pure internal/stdlib code, no new lib lookup needed. |
| 7 Plan | yes | yes | Codex produced 14 TASKs with per-task grep verification. |
| 8 Plan gate | yes | **no — rejected twice** | (a) Fetches-fallback for AC11 summary; (b) Wrong exception mapping in AC27 parametrized tests. Third pass APPROVE. |
| 9 Implementation (14 TASKs) | yes | yes (14/14 single-pass) | TASK 7 noted "already correct" — source already did single-parse before cycle 9; still tightened explicit `post.content` reuse. |
| 10 CI hard gate | yes | yes | 1999 passed; ruff clean. |
| 11 Security verify | yes | **no — rejected** | 2 gaps: unsplit secret literals in 2 test files; `_validate_wiki_dir` absent at new wiki_dir MCP surfaces. Fixed via 2 additional commits + 1 bearer split for a pre-existing cycle-1 test fixture (defensive). |
| 11.5 Existing-CVE patch | skipped — correct | yes | 0 open Dependabot alerts at pre-push re-read. |
| 12 Doc update | yes | yes | Codex produced CHANGELOG + BACKLOG deletions + CLAUDE.md stats + README in one pass. |
| 13 Branch + PR | yes | yes | PR #23 opened; 8 decision docs committed as separate audit-trail commit. |
| 14 PR review R1 | yes | partial | Codex R1 task runner hit usage limit and exited; fell back to Sonnet per skill policy. Sonnet architecture R1 + Sonnet edge-case R1 ran in parallel. 0 BLOCKERS, 2 MAJORS (AC21 runtime check missing, AC1 test vacuous). Fixed both. |
| 14 PR review R2 | yes | yes | Codex R2 APPROVE (Codex credits returned by then). |
| 15 Merge + cleanup + CVE warn | yes | yes | `--merge` method; 0 post-merge alerts. |
| 16 Self-review | (this document) | | |

## Lessons learned

### L1 — R1 test vacuousness via `if <cond>:` assertion gate

**Observation:** Cycle 9 R1 Sonnet edge-case review flagged that `test_search_pages_uses_override_vector_db` had `if calls:` gating the actual assertion. When `vec_path.exists()` returned False (because the test didn't seed the override DB), `calls` stayed empty, and the `if calls:` branch was skipped — test passed trivially. Reverting the fix would still cause the assertion to fire (via the poison PROJECT_ROOT monkeypatch catching the fallback path), so this was NOT a silent-failure case, but the TEST CONTRACT was weaker than intended.

**Generalization:** Any new regression test of the form
```python
results = prod_function(...)
if <something>:
    assert <contract>
```
needs scrutiny — if the `if` branch never fires during the happy path (or fires only via a side-effect unrelated to the AC), the test proves nothing about the AC.

**Durable rule:** Every new regression test's primary assertion must run UNCONDITIONALLY OR the conditional must be EXPECTED TO BE TRUE in the happy path. If a precondition (file existence, env setup) needs establishing, the test MUST seed it before the call under test.

**Skill patch:** Add as Red Flag row.

### L2 — Design-specified dual-mechanism enforcement can lose a mechanism in Codex Step 9

**Observation:** Cycle 9 AC21 design specified BOTH (a) module-level `assert CAPTURE_MAX_BYTES <= MAX_PROMPT_CHARS`, AND (b) runtime `if len(prompt) > MAX_PROMPT_CHARS: raise` inside `_extract_items_via_llm`. Codex Step 9 shipped (a) only; (b) was missed despite being explicit in Step 5's design condition 2. R1 Sonnet edge-case caught it.

**Why the miss:** Codex read the plan's TASK 9 bullet "AC21 — `MAX_PROMPT_CHARS = 600_000` ... raise `LLMError(...)`" — the ellipsis compressed the dual-mechanism contract. The `raise` clause technically implies runtime behaviour, but "module-level constant" and "runtime function body" are distinct code locations that Codex conflated.

**Durable rule:** When a single AC specifies multiple enforcement mechanisms (assert + runtime guard, try/except + fallback, lint check + unit test), the plan's TASK bullet must SEPARATE each mechanism as a sub-item so the implementing agent can't merge them. Write "AC21a: module-level assert" and "AC21b: runtime pre-flight guard" — two sub-ACs, one TASK.

**Skill patch:** Add as Red Flag row.

### L3 — Codex credit-limit mid-workflow → Sonnet fallback worked, but surface the expected cadence

**Observation:** PR #23 R1 Codex review hit "usage limit reached — try again after 8:46 PM". Per feature-dev skill "Codex unavailable → Sonnet fallback for code steps", I dispatched a Sonnet architecture review as fallback and a separate Sonnet edge-case review in parallel. Both completed cleanly and produced a coherent merge-ready verdict.

**What worked:** The skill's existing fallback policy is correct. The fallback Sonnet agent used the same per-axis checklist and produced the same output format (BLOCKERS/MAJORS/NITS/VERDICT).

**What to note:** R2 ran on Codex successfully 30 minutes later (credits returned). So the pattern is: R1 can fail-over to Sonnet; R2 often recovers to Codex. This is worth saying explicitly in the skill so future runs don't panic when R1 Codex fails.

**Skill patch:** Note in cross-agent prompt-hygiene section that credit exhaustion is a normal case with a known recovery.

### L4 — Security verify consistently catches path-validation gaps at new boundary points

**Observation:** Cycle 6 had similar. Cycle 7 had similar. Cycle 9 had the same gap: new `wiki_dir`-accepting MCP surfaces without path-containment validation. The security-verify agent reliably catches this; it's effectively a known gate. The new `_validate_wiki_dir` helper consolidates the fix; cycle 10 should migrate the remaining 4 callers (`kb_stats`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` — BACKLOG item added).

**Durable rule (cycle 7 R3 / cycle 8 R2 already covers this, refinement only):** when a cycle adds a new caller-supplied PATH parameter to an MCP tool (`wiki_dir`, `raw_dir`, `manifest_path`, arbitrary file/dir input), Step 5 design gate must require a validator at the MCP boundary OR explicitly justify absence. Step 11 security verify already enforces this — the new skill-level refinement is to add a `CONDITION:` entry in the Step 5 decision doc instead of discovering at Step 11.

**Skill patch:** Minor — strengthen the existing "same-class leak defence" guidance to call out path validation as a specific sub-class.

### L5 — Plan gate rejects are normal — expect 1-2 rounds

**Observation:** Cycle 9 plan gate rejected twice before APPROVE. Cycle 8 rejected twice. Cycle 7 rejected once. Cycle 6 rejected once. The pattern: Codex plan-gate catches (a) design contradictions (this cycle: AC11 fetches fallback), (b) test-coverage gaps (this cycle: AC27 wrong exception mapping; TASK 10 missing per-AC assertions).

**Takeaway:** Plan gate is doing its job. Don't view each reject as failure. Budget ~2 gate rounds into the cycle-9-through-N schedule.

**Skill patch:** none — this is expected behaviour.

## Red Flag patches

Two new entries for `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md` Red Flags table:

1. **"My regression test uses `if X: assert Y`" → _Vacuous test gate._** When the primary assertion is inside an `if <condition>:`, a False condition means the test passes without ever verifying the AC. Cycle 9 R1 lesson (AC1 vec_db test). Rule: either seed the precondition before the call, or invert — assert the condition is True first, THEN the contract. Reverting the fix must still fail the test.
2. **"Design specifies assert + runtime guard, I wrote the assert" → _Dual-mechanism collapse._** Any AC specifying multiple enforcement mechanisms (module-level assert + function-body guard, try/except + fallback, static check + dynamic check) must be split in the plan into AC-Na / AC-Nb sub-items so the Step 9 implementer can't merge them. Cycle 9 R1 lesson (AC21 MAX_PROMPT_CHARS). Rule: if Step 5 decision doc says "X AND Y", plan's TASK bullet must say "X (sub-a); Y (sub-b)" separately.

Patch committed at: (to be set after commit).
