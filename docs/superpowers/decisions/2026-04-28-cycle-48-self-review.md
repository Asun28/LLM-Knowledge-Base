# Cycle 48 — Self-Review (Step 16)

**Date:** 2026-04-28
**Cycle:** 48 (Test-quality upgrades + freeze-and-fold + dep-CVE re-confirm)
**PR:** [#71](https://github.com/Asun28/llm-wiki-flywheel/pull/71) merged at `6d6a88c`
**Branch:** `cycle-48-batch` (squashed)
**Worktree:** `D:/Projects/llm-wiki-flywheel-c48` (will be cleaned up)
**Wall-clock:** ~2h primary-session (start 12:25, merge 13:14)

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | partial (CVE only; threat model SKIP) | yes | — (skip-eligible per pure hygiene scope) |
| 3 — Brainstorming | SKIP (primary holds context, ≤16 ACs) | n/a | — (per cycle-37 L5) |
| 4 — Design eval (R1 DeepSeek) | yes | yes | DeepSeek background-PID dispatch silently failed initially (output file 0-byte for several min); had to re-check process |
| 5 — Design decision gate | yes (primary-session) | yes | — (per cycle-21 L1) |
| 6 — Context7 verification | SKIP (no third-party libs) | n/a | — |
| 7 — Implementation plan | yes (primary-session inline) | yes | — (per cycle-14 L1) |
| 8 — Plan gate | SKIP (subsumed in Step 5 design gate) | n/a | — |
| 9 — Implementation (TDD) | yes | **NO** | **AC2 first attempt failed: docstring-vs-code divergence per C41-L1** — production code matched python-frontmatter library convention (leading blank line + trailing-newline strip), but docstring claimed "verbatim". Fixed BOTH in same commit. |
| 9.5 — Simplify pass | SKIP (src/ diff is 7-line docstring, < 50 LoC) | n/a | — |
| 10 — CI hard gate | yes | yes | ruff format flagged 2 fold-target files (CRLF carryover per C35-L7) — applied formatter, recheck clean |
| 11 — Security verify + PR-CVE diff | yes | yes | EMPTY PR-introduced; threat model skipped (no scope) |
| 11.5 — Existing-CVE patch | SKIP (all 4 advisories `fix_versions=[]`) | n/a | — |
| 12 — Doc update | yes | yes | — (clean across 5 doc surfaces per C26-L2) |
| 13 — Branch finalise + PR | yes | yes | — |
| 14 — PR review (R1 + R2) | yes | yes | **R2 Codex flagged AC14 false-positive on cycle-13 L3 cosmetic preference** — line 91 (HIGH #4 progress note) correctly documented resolution by name, but tripped the strict zero-grep test. 1-line re-word cleared it. |
| 15 — Merge + cleanup | yes | yes | gh pr merge succeeded; --delete-branch failed because branch checked out in worktree (cycle-47 L2 known) |

## Surprises → Skill patches

### C48-L1 — DeepSeek background-PID dispatch via `&` from primary Bash silently disconnects stdout

**Cycle 48 evidence:** Step 4 R1 dispatch via `< /tmp/in.txt /c/Users/Admin/.claude/bin/deepseek ... > /tmp/c48-design-out.txt 2>&1 &` returned immediately with `Dispatched PID 263182`, but `/tmp/c48-design-out.txt` stayed at 0 bytes for >10 min while the python.exe child was still running. Only by `ps -ef | grep deepseek` could we confirm the model was actually executing. The redirect to /tmp worked once the child completed (~5min total). This is NOT the C42-L1 fabrication risk — DeepSeek genuinely ran and produced full 17KB output, just with delayed-write semantics through the Windows-bash backgrounding chain.

**Root cause:** Bash `&` backgrounds the wrapper script which exits immediately; Python.exe child runs detached. Output buffering plus the `tail -f`-incompatible redirect makes the output file appear empty until the child exits. Combined with `run_in_background=true` (which backgrounds the wrapper-of-wrapper), the parent reports "completed" while the actual model is still working.

**Self-check / workaround:**
- After backgrounding `deepseek` via `&` from a `run_in_background=true` Bash, the "completed" notification refers to the dispatcher exit, NOT the model. Always run `ps -ef | grep deepseek-cli` to confirm the child terminated before reading the output file.
- Schedule an explicit ScheduleWakeup (240-360s) to re-check, even if the parent reported completion. The actual output writes synchronously when the python child exits.
- Alternative: drop `&` from the inner command and rely solely on `run_in_background=true` for the Bash wrapper — single layer of backgrounding, output writes when the model returns.

**Refines:** cycle-39 L1 (wrapper fabrication) — that lesson covered FAKE output; this covers GENUINE output with delayed visibility. Companion to cycle-24 L5 (5-6 min dispatch budget).

### C48-L2 — Docstring-vs-code divergence on library-convention semantics is a high-yield C41-L1 trigger

**Cycle 48 evidence:** AC2 first attempt asserted `body_region == "\n" + body` based on `save_page_frontmatter` docstring's "Body content is preserved with interior bytes intact" claim. Test FAILED with `'\n\nLine 1...Line 4' != '\nLine 1...Line 4\n'`. The docstring's "verbatim" implication was technically false: `frontmatter.dumps` inserts a blank line BEFORE the body and STRIPS trailing newlines per python-frontmatter convention (verified by `default_handlers.py:157-163,238-243`).

**Root cause:** The docstring described intent ("body bytes intact") not actual library behavior. The production code was correct (matched library convention); the doc was idealized prose. C41-L1 specified this exact pattern: docstring-vs-code mismatch when upgrading vacuous tests, fix BOTH not just the test.

**Self-check before AC2-style upgrade:** When the upgrade-candidate test is "substring → exact equality" AND the production code delegates to a third-party library helper (`frontmatter.dumps`, `yaml.safe_dump`, `json.dumps`, `pickle.dumps`):
1. Run a 2-line REPL probe FIRST: construct a minimal input, call the library helper, print the bytes — observe what the library actually does.
2. Read the docstring of the wrapper. If it claims behavior different from what the REPL showed, the docstring is the bug.
3. Fix BOTH in same commit per C41-L1 — the new exact-equality test pins the actual library convention; the docstring augment describes the actual library convention.

**Generalizes:** C41-L1 (vacuous-test upgrade docstring sanity check). Specific subclass: library-delegation wrappers where the wrapper's docstring asserts properties the underlying library doesn't preserve. Common at boundaries between project code and `python-frontmatter` / `pyyaml` / `tomli` / `pickle` / etc.

### C48-L3 — Strict zero-grep AC14 contracts collide with audit-trail progress notes that reference resolved candidates by name

**Cycle 48 evidence:** AC14 design specified "remove BACKLOG.md HIGH lines 93-95" with implicit zero-grep contract `grep -nE "TestKbCreatePageHintErrors.*reload-leak|TestSaveFrontmatterBodyVerbatim.*under-asserted" BACKLOG.md` returning zero. The standalone bullets at lines 93-95 WERE deleted, but the AC15 HIGH #4 progress-note extension at line 91 documented the resolution BY NAME ("Cycle 48 also closed both ... TestKbCreatePageHintErrors reload-leak forward-protection (AC1) + TestSaveFrontmatterBodyVerbatim/AtomicWrite under-asserted upgrades (AC2+AC3) ..."). R2 Codex flagged this as MAJOR; per cycle-13 L3 it was cosmetic (semantically the line documents resolution, not open-state) but the strict grep contract did fail.

**Root cause:** AC14 (delete) and AC15 (extend progress note) were drafted independently. The progress note's natural phrasing referenced the resolved items by their full name — which IS the audit trail value of progress notes — but that phrasing also matches the AC14 zero-grep contract. The two ACs were in tension and only one could win without explicit coordination.

**Self-check at Step 5 design gate:** When AC pairs include (a) "remove text matching pattern P" AND (b) "extend audit-trail prose documenting the removed items", the design gate MUST specify a SHORTHAND form for (b) that does NOT match P. Recommended shorthand: cite the resolved candidates by AC number + cycle-N R2 spawn-source rather than by their original BACKLOG entry names. Example: replace "closed TestKbCreatePageHintErrors reload-leak (AC1)" with "resolved cycle-48+ candidates from cycle-47 R2 (AC1+AC2+AC3 detail in CHANGELOG-history.md cycle-48)". Then the audit-trail value survives AND the zero-grep test passes.

**Refines:** cycle-13 L3 (cosmetic post-hoc preferences) and cycle-23 L3 (BACKLOG promise enforcement). Specific to AC pairs that delete-and-document; check at Step 5 not Step 14.

## Patterns to preserve (clean rows)

- **Primary-session execution for ≤16-AC hygiene cycles** (cycle-37 L5): Steps 1-9 + 10-12 + 16 all primary-session, ~2h wall clock total. Codex/DeepSeek dispatch reserved for Step 4 R1 + Step 14 reviews only.
- **Worktree isolation from cycle-start** (cycle-42 L4): zero branch-discipline incidents; main worktree untouched throughout cycle.
- **Direct DeepSeek CLI** (cycle-39 L1): R1 design eval + R1 PR review both clean (modulo C48-L1 backgrounding gotcha).
- **Inline plan-gate** (cycle-21 L1): no Step 8 dispatch; design gate's CONDITIONS subsumed plan-gate role.
- **Project-relative `.data/cycle-48/` artifacts** (C40-L4): all baseline JSONs at project-relative paths; no /tmp on Windows traps.
- **Revert-verify before commit** (C40-L3): AC3 spy explicitly tested under reverted production code; FAIL → restored → PASS, locked in the contract.

## Cycle stats

- 8 commits total: 6 implementation + 1 R2 fix + 1 self-review (this commit)
- 16 ACs (15 numbered + AC16 implicit tag-bump scope)
- 1 src/ file modified (`src/kb/utils/pages.py` — 7-line docstring augment per C41-L1)
- 6 test files modified (4 + 2 deletions for folds)
- 7 doc files modified (BACKLOG, CHANGELOG, CHANGELOG-history, CLAUDE, README, 2 reference docs)
- 0 PR-introduced CVEs
- 0 BLOCKERS at R1/R2 (post-fix); 2 NITs (R1) + 1 cosmetic MAJOR (R2 doc-grep) addressed
- Tests: 3025 → 3025 preserved
- File count: 243 → 241 (cycle 48 brought stated/actual into alignment)
- Skill patches derived: 3 (C48-L1 backgrounding, C48-L2 library-delegation docstring divergence, C48-L3 zero-grep vs audit-prose tension)

## Operator follow-up (out of repo scope)

The 3 skill patches above are documented here in the project repo. The actual `~/.claude/skills/dev_ds/references/cycle-lessons.md` updates and SKILL.md "Accumulated rules index" entries belong in user-global `~/.claude/skills/` per C39-L5 — operator should:
1. Append the C48-L1/L2/L3 blocks to `~/.claude/skills/dev_ds/references/cycle-lessons.md` under `## Cycle 48 skill patches (2026-04-28)`.
2. Add 3 one-liners to SKILL.md "Accumulated rules index" under their concern areas:
   - "Subagent dispatch and fallback" → C48-L1
   - "Test authoring — ensure a production revert fails the test" → C48-L2 (refines C41-L1)
   - "Docs and count drift" → C48-L3 (refines cycle-13 L3 + cycle-23 L3)
