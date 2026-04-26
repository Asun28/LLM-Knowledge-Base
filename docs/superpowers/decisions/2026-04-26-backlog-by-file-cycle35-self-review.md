# Cycle 35 — Step 16 Self-Review

Date: 2026-04-26
PR: [#49](https://github.com/Asun28/llm-wiki-flywheel/pull/49) merged at `f8f72ac`
Commits: 14 cycle-35 + 1 merge = 15
Tests: 2941 → 2995 (+54 passed; 10 skipped unchanged)

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | no | `python -m pip_audit` failed (no module). Use `pip-audit` binary. |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval (R1 Opus + R2 Codex parallel) | yes | no | R1 ~3min, R2 ~8min — needed second 240s wake (cycle-24 L5 option b). |
| 5 — Design decision gate (Opus) | yes | yes | 13 questions resolved cleanly. |
| 6 — Context7 verification | yes | no | R2's Playwright snippet used `browser.new_page(viewport=)` shortcut; Context7 confirmed `browser.new_context(viewport=)` is canonical. Updated to canonical form. |
| 7 — Implementation plan (primary) | yes | yes | Drafted in primary per cycle-14 L1; ~10 min. |
| 8 — Plan gate (Codex) | yes | no | REJECT with 5 doc/design gaps; resolved inline per cycle-21 L1. |
| 9 — Implementation (4 file groups, primary) | yes | no | Mid-implementation REPL revealed an EXISTING drive-letter pattern over-match (URL collision) that no prior test had caught. Added same-class peer fix (`(?<![A-Za-z])` lookbehind) in same cycle-35 commit. |
| 9.5 — Simplify pass | yes | no | 1 actionable finding (`_FILENAME_MAX_LEN` constant dedup); 4 false-positives. |
| 10 — CI hard gate (full suite) | yes | no | `ruff format --check` flagged 4 NON-cycle-35 files (CRLF/LF carryover); fixed as separate `chore(ruff)` commit. Full pytest revealed 3 stale doc-anchor tests still pointing at CLAUDE.md after cycle-34's split into docs/reference/* (commit 518db0e). Re-anchored to the new files. |
| 11 — Security verify (Codex) | yes | yes | T9 PARTIAL was a stale snapshot (Codex ran before GitPython commit landed). Effectively APPROVE. |
| 11b — GitPython bump | yes | yes | Class-A patch landed cleanly; pip-audit confirms GitPython advisories absent. |
| 12 — Doc update (primary) | yes | yes | Drafted in primary per cycle-13 L2 (mechanical). |
| 13 — Branch finalise + PR | yes | no | block-no-verify hook over-matched commit message containing "verified" word — re-worded. |
| 14 — PR review (R1+R2+R3) | yes | no | (a) R1 Sonnet first dispatch failed with `400 Could not process image` on PR PNG — re-dispatched with no-binary instruction. (b) R3 ran in parallel with R2, read stale threat-model.md before R2's parallel update landed. (c) R1 Sonnet caught a real MAJOR (slash-UNC over-matched 2-segment prose like `// comment/block`); fixed via 3-segment requirement. |
| 15 — Merge + late-arrival CVE warn | yes | yes | No new advisories during cycle. 6 open Dependabot alerts unchanged from baseline (3 GitPython will auto-close after re-scan; 2 litellm + 1 ragas remain narrow-role-exception). |
| 16 — Self-review + skill patch | in progress | — | — |

## Skill patches

7 surprises this cycle → 7 candidate L1/L2/L3 lessons. Prioritising the highest-value 7 to append to `references/cycle-lessons.md`:

### C35-L1 — `python -m pip_audit` doesn't work; use `pip-audit` binary directly
**Rule.** The pip-audit tool is exposed as a console script `pip-audit` (with hyphen), NOT as a Python module addressable via `python -m pip_audit`. Running `python -m pip_audit ...` fails with `No module named pip_audit` because the package's import name is `pip_audit` but it has no `__main__.py` entry point.
**Why.** Lesson 2026-04-26 cycle 35 Step 2: my `python -m pip_audit --format json > baseline.json` returned exit 1 with `No module named pip_audit`; the JSON was empty; cycle-22 L1 (silent baseline-empty footgun) almost fired again.
**Self-check.** Use the binary path directly: `D:/Projects/llm-wiki-flywheel/.venv/Scripts/pip-audit.exe --format json` (Windows) or `.venv/bin/pip-audit --format json` (POSIX). Do NOT use `python -m`.
**Refines.** Cycle-22 L1 (baseline-capture footguns) — adds the invocation form to the watch list.

### C35-L2 — R2 Codex with checklist-heavy prompts can take 8+ min
**Rule.** When R2 Codex's prompt enumerates ≥8 numbered checks (Q1, Q2, Q3, ...), budget 8-10 minutes for completion (vs cycle-24 L5's 5-6 min default). Each numbered check often triggers a separate read+grep round inside Codex.
**Why.** Lesson 2026-04-26 cycle 35 Step 4: R1 Opus took ~3 min (8 reads + 5 greps); R2 Codex with 10-point adversarial checklist took ~8 min. The ScheduleWakeup option (b) — second 240s wake — handled this gracefully but with one polling check-in.
**Self-check.** When R2 prompt has ≥8 numbered concerns, default to schedule 270s wake + EXPECT a second 240s wake. For 5-7 concerns, cycle-24 L5 option (a) is fine.
**Refines.** Cycle-24 L5 (subagent timing budget) — adds prompt-complexity adjustment.

### C35-L3 — Same-class peer scan EXTENDS to existing patterns when adding to a regex family
**Rule.** When adding a new alternative to an existing regex `(A)|(B)|(NEW)`, REPL-probe inputs that should match NEW and confirm they don't get OVER-matched by A or B. If any existing alternative over-matches, add a same-cycle peer fix + negative test.
**Why.** Lesson 2026-04-26 cycle 35 Step 9: extending `_ABS_PATH_PATTERNS` for slash-UNC, my REPL probe `sanitize_text("see https://example.com/path")` revealed the EXISTING drive-letter alternative `(?:[A-Za-z]:[\\/][^\s'\"]+)` already over-matched URLs (`s://example.com/path` collapsed to `<path>`). Pre-existing since cycle 18 AC13; no prior test had caught it. Same-class peer fix `(?<![A-Za-z])` lookbehind landed in cycle-35's first commit (`39aa787`).
**Self-check.** At Step 9, when adding a new alternative to an existing regex, REPL-test 3-5 inputs spanning the regex family. If any existing alternative misbehaves (over-match, under-match), add a same-cycle peer fix BEFORE the new alternative ships.
**Refines.** Cycle-16 L1 (same-class peer scan in Step 11 fixes) — extends to Step-9 implementation phase.

### C35-L4 — `block-no-verify` hook regex matches "verify" substring anywhere in bash commands
**Rule.** The `block-no-verify` hook (cycle-22 L2 documented) over-matches the substring `verify` (or `verified` / `verification`) anywhere in the bash command, NOT just `--no-verify` flag. Commit messages containing prose like `"PNG verified: 1.59 MB"` get BLOCKED at hook level, not at git level.
**Why.** Lesson 2026-04-26 cycle 35 Step 13: my commit message `"PNG verified: 1.59 MB, v0.11.0 visible in rendered title block."` was rejected with `BLOCKED: --no-verify flag is not allowed`. The hook scans the entire bash command string; the heredoc content is part of the string.
**Self-check.** Before committing with a message containing "verif", scan for `--no-verify` (the actual flag); if absent, re-word the message to avoid the trigger. Common safe substitutions: `verified` → `confirmed` / `validated`; `verification` → `check` / `audit`.
**Refines.** Cycle-22 L2 (block-no-verify intercepts companion-script source) — adds commit-message prose as a third trigger surface.

### C35-L5 — Sonnet/Opus PR reviewer fails with `400 Could not process image` on binary PR diffs
**Rule.** When dispatching Sonnet or Opus reviewers on a PR diff that includes binary files (PNG, PDF, SVG, etc.), the agent attempts to read the binary via Read and crashes with `400 invalid_request_error: Could not process image`. Re-dispatch with explicit `DO NOT READ BINARY/IMAGE FILES` instruction + use `git diff -- '*.py' '*.md' '*.txt'` glob filter to gate them out.
**Why.** Lesson 2026-04-26 cycle 35 Step 14: PR #49 contained `docs/architecture/architecture-diagram.png` (1.59 MB). R1 Sonnet first dispatch (no-binary instruction absent) crashed at ~7 min wall-clock with the image error. Re-dispatch with explicit no-binary instruction succeeded.
**Self-check.** Before dispatching a PR-review subagent, run `git diff --stat origin/main..HEAD | grep -i bin` to identify binary files. If any are present, prepend the prompt with `DO NOT READ BINARY/IMAGE FILES. Use git diff with text-only glob filters.`
**Refines.** Cycle-22 L2 (forwarding-agent failure modes) — adds binary-file image-API failure to the catalog.

### C35-L6 — Parallel R2/R3 reviewer race: R3 reads stale doc before R2's parallel update lands
**Rule.** When dispatching R2 + R3 in parallel where R2 is EXPECTED to make doc edits (e.g., threat-model amendments per cycle-23 L3 deferred-promise enforcement), R3 may read a stale snapshot of the doc and report a fix that R2 already applied. Either (a) wait for R2 to complete BEFORE dispatching R3, or (b) accept that R3 may need post-completion reconciliation against current main.
**Why.** Lesson 2026-04-26 cycle 35 Step 14: I dispatched R2 Codex (verify R1 fixes + update threat-model T1b annotation) and R3 Sonnet (synthesis + audit-doc drift check) in parallel. R3 finished first (~3.6 min); R2 finished later (~4.7 min). R3's audit-doc check read threat-model.md BEFORE R2 had updated lines 18 and 50, so R3 flagged T1b annotation as stale. By the time I read R3's verdict, R2 had already updated the file. Cost: ~30 seconds to verify R3's finding was already addressed.
**Self-check.** When R2 prompt explicitly instructs doc edits, EITHER serialise (R2 first, then R3) OR add to R3 prompt: "R2 may have already updated docs in parallel — re-read any audited doc IMMEDIATELY before flagging stale text". Option (a) is safer, option (b) is faster.
**Refines.** Cycle-19 L4 (R3 audit-doc drift first focus) — adds parallel-race awareness.

### C35-L7 — `ruff format --check` Step-10 surfaces non-cycle CRLF/LF carryover that must still be cleaned
**Rule.** The `ruff format --check` gate at Step 10 may flag files NOT touched by the cycle's own diff if they have CRLF/LF mixing or pre-existing format drift carried over from prior Windows checkouts. Per cycle-34 L6 (Step-10 must mirror full CI), these must be cleaned in the cycle even if not authored — typically as a separate `chore(ruff)` commit so the audit trail is clear.
**Why.** Lesson 2026-04-26 cycle 35 Step 10: full `ruff format --check src/ tests/` flagged 4 files (`src/kb/capture.py`, `src/kb/mcp/app.py`, `src/kb/mcp/quality.py`, `tests/test_capture.py`) for mixed CRLF/LF. None were authored by cycle 35. Fixed as `4283074 chore(ruff, cycle 35): normalize line wrapping in tests/test_capture.py`. Subsequent `git stash` / `git stash pop` race re-introduced unrelated stash content; resolved by `git checkout HEAD --` on the unmerged files.
**Self-check.** At Step 10, run `git stash list` to confirm no stale stashes BEFORE running any `git stash` for diagnostic purposes. If `ruff format --check` flags non-cycle files, accept the carryover-fix commit as part of cycle hygiene; do NOT skip the gate.
**Refines.** Cycle-34 L6 (Step-10 local gate must mirror CI) — adds carryover-cleanup expectation.

## Index entries to add to SKILL.md

Per skill instructions, add one-liners to `Accumulated rules index` under the appropriate concern areas:

- **Library and API awareness:** `- C35-L1 — pip-audit binary, NOT \`python -m pip_audit\` (refines cycle-22 L1)`
- **Subagent dispatch and fallback:** `- C35-L2 — R2 Codex with ≥8 numbered checks → budget 8-10 min (refines cycle-24 L5)`
- **Scope and same-class peers:** `- C35-L3 — same-class peer scan EXTENDS to existing patterns when adding to a regex family (refines cycle-16 L1)`
- **Subagent dispatch and fallback:** `- C35-L4 — block-no-verify hook over-matches "verify" substring in commit prose (refines cycle-22 L2)`
- **Subagent dispatch and fallback:** `- C35-L5 — Sonnet/Opus reviewer fails on binary-file PR diffs; explicit no-image instruction needed (refines cycle-22 L2)`
- **Subagent dispatch and fallback:** `- C35-L6 — parallel R2/R3 race when R2 makes doc edits; serialise OR accept R3 stale-snapshot reconciliation (refines cycle-19 L4)`
- **CI hard-gate hygiene:** `- C35-L7 — Step-10 \`ruff format --check\` may flag non-cycle CRLF carryover; clean as separate \`chore(ruff)\` commit (refines cycle-34 L6)`

## What ran clean (no surprises)

Steps 1, 3, 5, 7, 11b, 12, 15. These are now reliable steps; their first-try success rate is high enough that I should defer skill-patch attention elsewhere.
