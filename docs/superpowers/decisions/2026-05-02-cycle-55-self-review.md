# Cycle 55 — Self-review scorecard + 5 skill-patch lessons (C55-L1..L5)

**Date:** 2026-05-02
**Pipeline:** `dev-mimo-opus` (project trial — first real-cycle exercise)
**Branch:** `cycle-55-self-review` (off `origin/main` @ 7c20f5d, the cycle-55 squash-merge of PR #76)
**Final test count:** 3026 (3015 passed + 11 skipped on Windows local)
**Final file count:** 221

## Step Scorecard (Steps 1-23)

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + AC | yes | yes | — |
| 2 — Threat model | skipped (pure refactor) | — | — |
| 2 — Dep-CVE baseline | yes | no | C34-L1 fired (pip-audit live env, NOT `-r requirements.txt`); plan-gate caught the design-doc command discrepancy |
| 3 — Brainstorming | skipped (pattern fixed) | — | — |
| 4 — Design eval | skipped (trivial folds) | — | — |
| 5 — Design decision gate | yes (primary) | yes | Q1 "BOTH-tests" requirement was clear in design doc but easy to lose track of during impl — see C55-L1 |
| 6 — Context7 | skipped | — | — |
| 7 — Plan | yes (primary, NOT MiMo) | yes | `mimocoding-rescue` not in active subagent set; primary session was correct call per cycle-13 L2 |
| 8 — Plan gate | yes (Codex fallback) | no | First MiMo trial substitution; Codex returned REJECT 5 gaps (4 doc + 1 PLAN-AMENDS-DESIGN); all closed inline per C21-L1 |
| 9a — Fold graph_fixes | yes | yes | — |
| 9b — Fold evolve_fixes | yes | yes | — |
| 9c — Fold ingest_aux_fixes | yes | yes | — |
| 9d — Fold review_feedback_fixes | yes | yes | host-shape preservation Q2 decision easy to apply |
| 10 — Simplify | skipped (signature-preserving) | — | — |
| 11 — SAST + secrets | skipped (test-only) | — | — |
| 12 — CI hard gate + SCA | yes | yes | full suite + ruff + pip-audit clean |
| 13 — Coverage delta | skipped (test fold) | — | — |
| 14 — Security verify | skipped (Step 2 skipped) | — | — |
| 15 — Existing-CVE patch | attempted | NO | litellm 1.83.7 silent-downgrades python-dotenv → introduces CVE-2026-28684; reverted; new BACKLOG insight — see C55-L4 |
| 16 — IaC/SBOM | skipped (no manifests) | — | — |
| 17 — Doc update | yes (primary, NOT MiMo) | yes | `mimochat-rescue` not in active subagent set; primary correct |
| 18 — Branch finalise + PR | yes | yes | — |
| 19 — Signed commits | skipped (repo doesn't enforce) | — | — |
| 20 — PR review R1 | yes (DeepSeek + Sonnet) | NO | Both reviewers caught AC1 design-deviance MAJOR (Q1 spy upgrade not implemented); fixed in 59a4b1c — see C55-L1 |
| 20 — PR review R2 | yes (Codex + Sonnet) | NO | Codex caught monkeypatch-vs-try/finally MAJOR; Sonnet caught 2 doc-drift MINORs; fixed in 5be584e — see C55-L2 + C55-L5 |
| 21 — Merge + cleanup | yes | yes | merge-time `gh pr merge` failed with worktree conflict but PR DID merge on remote (origin/main advanced b3132e3 → 7c20f5d); local cleanup deferred to user (worktree remove permission-denied with files held; left for user to clean) |
| 21 — Late-arrival CVE warn | yes | yes | alerts 12-15 same as baseline; no new advisories during cycle |
| 22 — Deploy approval gate | skipped (no artifact) | — | — |
| 23 — Post-deploy smoke | skipped (Step 22 skipped) | — | — |

**Step 24 (this self-review):** in progress.

## Cycle 55 skill patches (2026-05-02)

5 lessons derived from cycle 55's surprises. Each lesson has the rule, the why, and the how-to-apply. Lessons should propagate to `.claude/skills/dev-mimo-opus/references/cycle-lessons.md` when that file is committed.

### C55-L1 — Design Q1 "TWO tests" must be enumerated as TWO ACs in Step 7 plan

**Rule.** When Step 5 design Q-decision text uses conjunctions ("X AND Y", "rename to A; add separate test B", "spy + orphan"), the Step 7 plan must list each conjunct as its own bullet with its own test verification. Plan gate must scan for design conjunctions and verify each has a corresponding plan task.

**Why.** Cycle-55 R1 DeepSeek + Sonnet both flagged AC1 as design-deviance MAJOR: design.md Q1 said "behavioral spy + separate orphan test" (two tests) but implementation collapsed to one renamed test. Plan-gate caught 5 doc-clarification gaps but missed the implicit two-test split because the plan text said "Move 3 tests, with Q1 upgrade applied to test 1" — a single bullet describing two distinct artifacts. The R1 catch cost an extra fix-commit (59a4b1c) plus two more reviewer passes.

**How to apply.** Plan-gate prompt addition: "For every Q-decision whose text contains 'AND', 'plus', 'add separate', 'rename + add', or 'two', verify each conjunct has its own plan task with its own test verification." Self-check before commit: grep design.md Q-decision sections for these conjunction tokens; for each hit, count plan tasks that match. Mismatches flag as PLAN-AMENDS-DESIGN per cycle-11 L3.

**Refines:** cycle-21 L2 (Step 14 catches design-implementation drift), cycle-22 L5 (design-gate CONDITIONS are load-bearing test coverage).

---

### C55-L2 — pytest's monkeypatch fixture preferred over manual try/finally for class-level patches

**Rule.** When a test needs to patch a class-level attribute (method, descriptor, property), prefer pytest's `monkeypatch.setattr(Class, "attr", spy)` over manual `try: Class.attr = spy ... finally: Class.attr = orig` patterns.

**Why.** Cycle-55 R2 Codex flagged the AC1 R1-fix's manual try/finally class-level patching as a leak-risk. My reading was the finally restoration runs unconditionally so leak risk was theoretical-only — but pytest's monkeypatch handles auto-restoration on KeyboardInterrupt, test-collection abort, and subprocess fork errors that try/finally can miss in edge cases. The refactor (5be584e) is unambiguously safer and reduces the test body by ~7 lines.

**How to apply.** Self-check before commit: grep new test files for `Class.attr =` or `class-level attribute assignment` followed by `try` blocks; if any hit, ask "could this use `monkeypatch.setattr` instead?" — almost always yes. The fixture is added by including `monkeypatch` as a test parameter (`def test_X(monkeypatch): ...`).

---

### C55-L3 — `mimo*-rescue` agents need explicit registry availability check at cycle start

**Rule.** Before the first MiMo dispatch in a cycle (Step 7 plan, Step 8 plan-gate, Step 17 doc-update), perform a lightweight pre-flight check: dispatch a trivial `Agent(subagent_type="mimocoding-rescue", description="ping", prompt="reply 'ok'")`. If the dispatch returns a "subagent_type not found" error, document the substitution at the cycle's first dispatch point and budget primary-session execution for all MiMo-tagged steps.

**Why.** Cycle-55 was the first real-cycle exercise of the dev-mimo-opus skill. The MiMo agents (`mimocoding-rescue`, `mimochat-rescue`) are documented as available in the user-scope registry but were NOT loaded in this Claude Code session's active subagent set (system-reminder did not list them). Step 8 plan-gate dispatch fell back to `codex:codex-rescue` per the skill's trial-fallback chain. This worked but means MiMo-specific dispatch hygiene (Token Plan TOS, Singapore region lock, hard-stop-on-401) got zero exercise this cycle.

**How to apply.** Update the dev-mimo-opus skill's "Trial-fallback chain" section to note: "First-cycle expectation is that MiMo agents may be unregistered — primary-session fallback per cycle-13 L2 sizing heuristic is the trial's effective default until the agents are universally loaded." Also: at Step 24 self-review, the trial writeup should distinguish "MiMo agent quality data points" (zero this cycle) from "skill framework fitness data points" (full validation, every step worked end-to-end).

**Refines:** dev-mimo-opus SKILL.md "Trial-fallback chain" + "MiMo dispatch hygiene" sections.

---

### C55-L4 — Step-15 dep-CVE patch must check transitive pin trade-offs BEFORE applying

**Rule.** Before Step 15 commits a dep-CVE patch:
1. Run `pip install --dry-run --upgrade <patched_pkg>` and inspect for "Successfully installed" + "but you have X which is incompatible" warnings.
2. Capture predicted post-install state via a hypothetical `pip-audit` (run from a clone venv if dry-run-pip-audit isn't available).
3. If the predicted state introduces NEW advisories not in the baseline (Class B PR-introduced), abort the patch and BACKLOG-defer per cycle-22 / cycle-29 / cycle-55 precedent.

**Why.** Cycle-55 attempted litellm 1.83.0 → 1.83.7 (3 GHSAs patchable). Pip silently downgraded click 8.3.2 → 8.1.8, importlib-metadata 8.7.1 → 8.5.0, jsonschema 4.26.0 → 4.23.0, AND python-dotenv 1.2.2 → 1.0.1 to satisfy litellm 1.83.7's hard-pins. The python-dotenv downgrade introduced CVE-2026-28684 / GHSA-mf9w-mj56-hr94 (HIGH symlink attack on `set_key` / `unset_key`). Step 14 default REJECTs PR-introduced advisories — patch reverted. The downgrade was VISIBLE at install time (pip's "but you have X which is incompatible" warning) but not flagged by Step 15's flow because the flow assumed install + commit + audit, not pre-flight dry-run.

**How to apply.** Step 15 skill text update: insert "pre-flight dry-run check" between "bump the pin" and "install + audit". Self-check: any `pip install --upgrade` output containing "Successfully installed <multiple packages>" where only ONE was the target indicates silent downgrade — investigate the cascade before committing the requirements.txt change.

**Refines:** cycle-22 L1 (pip-audit live-env vs `-r requirements.txt`), cycle-29 (transitive constraints).

---

### C55-L5 — R1 NIT BACKLOG-marker filing convention is binding

**Rule.** When R1 / R2 flags NIT candidates that route to "cycle-N+M filing", IMMEDIATELY file the BACKLOG entry as part of the R1-fix or R2-fix commit. Don't defer to "later". A single consolidated entry per discovery cycle is fine (cycle-55's batch of 5 sites went into one entry per R2 Sonnet's recommendation).

**Why.** Cycle-55 R1 Sonnet flagged 5 cycle-56+ getsource candidates as NIT. The R1-fix commit message said "filed at cycle-56+ filing time" — but didn't actually file. R2 Sonnet caught this — the cycle-52 → cycle-53+ test_prune_base precedent shows R1-flagged NITs ARE filed in BACKLOG.md as upgrade markers even when deferred. Omitting the BACKLOG entry creates a discovery gap if cycle-56+ doesn't explicitly re-run the same scan.

**How to apply.** Self-check before R1-fix commit: if the review verdict text contains "cycle-N+M filing time" or "recommend cycle-N+M filing", the commit's BACKLOG.md diff MUST contain a corresponding entry. R2-catchable miss otherwise. Update plan-gate prompt to verify R1 NIT dispositions include BACKLOG entries.

**Refines:** cycle-52 → cycle-53+ test_prune_base BACKLOG-marker convention; this cycle elevates it from precedent to rule.

---

## First MiMo trial data points (for 2026-05-31 writeup)

These observations feed the end-of-May trial writeup comparing MiMo vs DeepSeek vs Codex vs Sonnet vs Opus. Cycle 55 was the FIRST real-cycle exercise of the project-scoped `dev-mimo-opus` skill.

### Agent registration

- `mimocoding-rescue` and `mimochat-rescue` NOT in active subagent set this Claude Code session. Pre-flight check (per C55-L3) would have surfaced this in <10s.
- Per the skill's trial-fallback chain, MiMo-tagged steps fall back to `codex:codex-rescue` (Step 8) or primary session (Steps 7, 9, 17) per cycle-13 L2 sizing heuristic.

### Dispatch outcomes

| Step | Spec dispatch | Actual dispatch | Time | Outcome |
|------|---------------|-----------------|------|---------|
| Step 8 plan-gate | `mimocoding-rescue` @ mimo-v2.5-pro | `codex:codex-rescue` | ~106s | REJECT 5 gaps (4 doc + 1 PLAN-AMENDS-DESIGN); all closed inline per C21-L1 |
| Step 7 plan | `mimocoding-rescue` @ mimo-v2.5-pro | primary session | ~5 min | Plan written + committed; cycle-13 L2 sizing heuristic correct call |
| Step 9 implementation (×4) | `mimocoding-rescue` impl + `mimocoding-rescue` background reviewer | primary session | ~5 min total | 4 folds done + 1 R1-fix + 1 R2-fix; zero MiMo dispatch attempted (sizing heuristic) |
| Step 17 doc update | `mimochat-rescue` @ mimo-v2-flash | primary session | ~2 min | Doc-sync done; cycle-13 L2 sizing heuristic correct call |
| Step 20 R1 | DeepSeek + Sonnet | as specified | ~169s + ~167s parallel | DeepSeek REQUEST-CHANGES on AC1 + APPROVE on AC2-9; Sonnet MAJOR + MINOR + NIT |
| Step 20 R2 | Codex + Sonnet | as specified | ~344s + ~224s parallel | Codex REQUEST-CHANGES (FOCUS-3 monkeypatch + FOCUS-5 count drift); Sonnet APPROVE WITH MINOR AMENDMENTS |

### Token Plan / cost data

- Cumulative MiMo Token Plan burn: ZERO (no MiMo agent invocations).
- Cumulative DeepSeek burn: 1 dispatch (R1 architecture).
- Cumulative Codex burn: 2 dispatches (Step 8 plan-gate fallback + R2 architecture).
- Cumulative Sonnet (`everything-claude-code:code-reviewer`) burn: 2 dispatches (R1 + R2 edge-cases).
- Cumulative Opus burn: zero subagent dispatches; primary session (orchestrator) only.

### Skill framework fitness (vs MiMo agent quality)

- The skill's 24-step pipeline executed end-to-end without structural gaps.
- The trial-fallback chain (`mimo*-rescue → Codex → Sonnet → primary`) worked correctly at every step that needed it.
- The Step 20 R1+R2 routing (DeepSeek + Codex + Sonnet, MiMo-independent per skill spec) caught 2 MAJORs and 3 MINORs across two rounds.
- The cycle-13 L2 sizing heuristic + C37-L5 primary-session default kept overhead low for a 4-fold cycle.
- C55-L3 captures the "pre-flight check" gap so future cycles avoid the silent-substitution surprise.

### Recommendation for 2026-05-31 writeup

Cycle 55 validates the **skill framework** but provides ZERO data on MiMo agent quality. Subsequent cycles must either:
1. Pre-flight load the MiMo agents (per C55-L3) and exercise them at Steps 7, 9, 17, OR
2. Document that MiMo-tagged steps continue to run via fallback, and the trial's effective question becomes "is the dev-mimo-opus skill's fallback chain correct?" (answer so far: yes).

A meaningful MiMo-vs-Codex comparison requires at least one cycle where MiMo actually executes the dispatched work.

---

## Closing

- PR #76 merged at 7c20f5d on 2026-05-02 00:18:36 UTC.
- 9 commits total: c11b7dc + 5e966ad + 3ac38b4 + d6e1d0a + e701a6a + 384bbb4 + 17f241e + 59a4b1c + 5be584e (squashed into 7c20f5d).
- Final Windows local: 3015 passed + 11 skipped + 48 warnings in 135.46s. ruff clean.
- BACKLOG hand-offs to cycle-56+: `test_review.py::test_embedding_dim_resolved` triple-escape-hatch sentinel + 5 unflagged getsource sites batch-filing.
- 5 skill patches (C55-L1 through C55-L5) ready to propagate to `.claude/skills/dev-mimo-opus/references/cycle-lessons.md` when that file is committed.

Cycle 55 complete.
