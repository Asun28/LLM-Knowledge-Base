---
title: "Cycle 7 — Step 16 self-review"
date: 2026-04-18
type: self-review
feature: backlog-by-file-cycle7
---

# Cycle 7 — Step 16 Self-Review

## Scorecard

| Step | Executed? | First-try clean? | Surprised by anything? |
|------|-----------|------------------|------------------------|
| 1 — Requirements + AC | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | yes | pip-audit resolver conflict on existing `requests==2.33.0` pin — pre-existing env issue, documented |
| 3 — Brainstorming | yes (inline, 3 approaches) | yes | — |
| 4 — Design eval 2 rounds parallel | yes | yes | Codex R1 caught AC12 under-scoping (14 sites, not 5); AC23 sentinel-name mismatch |
| 5 — Design decision gate | yes | yes | 14 OQs resolved autonomously, 0 ESCALATE |
| 6 — Context7 verification | skipped (stdlib/internal) | N/A | — |
| 7 — Plan | yes (written directly to decisions file) | yes | — |
| 8 — Plan gate | yes | **REJECT** → 3 minor gaps patched in-place (no re-dispatch) | — |
| 9 — Implementation TDD | yes | close; 3 legacy tests needed updates | 5 ACs ended up already shipped; autouse embeddings reset broke one pre-existing test via unexpected HF-API call during teardown (pre-existing) |
| 10 — CI hard gate | yes | needed 2 ruff-format rounds | 7 files reformatted after Edits |
| 11 — Security verify | yes | **REJECT** → 4 blockers patched | Codex caught 4 residual raw `{e}` sites in `mcp/core.py` beyond my scoped 5 |
| 12.5 → 12 reorder | **yes — user mid-cycle correction** | n/a (one-time reorder) | User flagged: Step 12.5 must run BEFORE Step 12 so docs capture any dep bumps in one pass. Saved to memory + will patch skill |
| 12.5 — Existing-CVE patch | yes | yes (no-op) | 0 open alerts → no bumps required |
| 12 — Doc update | yes | yes | Codex cleaned up BACKLOG.md; 26 resolved bullets deleted, 3 partial items kept with cycle-7 notes |
| 13 — Branch finalise + PR | yes | yes | PR #21 opened cleanly |
| 14 — PR review (3 rounds) | yes (full 3 rounds for >25 items) | R1 REJECT, R2 REJECT, R3 REJECT (then APPROVE) | R3 caught venv-subprocess `PYTHONPATH` gap — tests that pass locally via pytest's `pythonpath=["src"]` config fail in subprocess spawn without env override |
| 15 — Merge + cleanup | yes | yes | 0 late-arrival alerts between Step 12.5 and post-merge |
| 16 — Self-review + skill patch | yes (this doc) | yes | — |

Overall: **8 commits + 4 PR-review follow-up commits = 12 commits**. 1868 → 1919 tests (+51). 0 PR-introduced CVEs. Single user correction mid-cycle (Step 12.5/12 reorder) surfaced a real skill bug worth patching.

## Meta-lessons

### 1. Step 12.5 must precede Step 12 in the skill (USER CORRECTION mid-cycle)

The current SKILL.md pipeline table orders Step 12 → Step 12.5. Mid-cycle the user said: "wrong order — should patch then doc update". Rationale: if docs update first, then a dep bump lands, the CHANGELOG/BACKLOG are immediately out of sync — the doc pass must be redone. Patching first makes the single Codex doc pass capture BOTH the code diff AND any dep bumps.

**Action for Step 16 skill patch**:
- Swap the two rows in the pipeline table.
- Rewrite the "Moved here" note at the top of the Step 12.5 body ("Runs AFTER docs" → "Runs BEFORE docs").
- Update the Codex Step 12 doc prompt to explicitly expect dep-bump commits from Step 12.5 (already partially handles this — now the narrative matches).

Memory saved at `C:\Users\Admin\.claude\projects\D--Projects-llm-wiki-flywheel\memory\feedback_cve_patch_before_docs.md`.

### 2. `frontmatter.dumps` alphabetizes metadata by default

My AC29 migrated `_write_wiki_page` from hand-rolled f-string YAML to `frontmatter.Post` + `frontmatter.dumps`. R1 Codex M3 caught that the dumped field order became alphabetical (`confidence, created, source, title, type, updated`) instead of insertion order (`title, source, created, updated, type, confidence`). Downstream parsers that implicitly depend on the old order would regress silently.

Fix: pass `sort_keys=False` to `frontmatter.dumps()`. The frontmatter library passes kwargs to the underlying `yaml.safe_dump`.

**Action for Step 16 skill patch**:
- Add a Red Flag row: when migrating hand-rolled YAML to `frontmatter.dumps`, ALWAYS pass `sort_keys=False` — the library defaults to alphabetizing.

### 3. Subprocess-probe tests need explicit PYTHONPATH

R3 Codex found that `TestCliVersionShortcircuit::test_version_does_not_trigger_kb_config_import` fails at run time with `ModuleNotFoundError: kb` in the subprocess, even though the pytest parent process can import `kb` fine. Root cause: pytest's `pythonpath = ["src"]` config adds `src/` to `sys.path` for the parent but doesn't propagate to spawned subprocesses. The editable install (`pip install -e .`) is brittle — it depended on `.venv` being in a specific state.

Fix: pass `env={**os.environ, "PYTHONPATH": "<repo>/src" + os.pathsep + os.environ.get("PYTHONPATH", "")}` to every subprocess test.

**Action for Step 16 skill patch**:
- Add a Red Flag row: when a cycle-specific test uses `subprocess.run([python, -c, ...])`, the child interpreter does NOT inherit pytest's `pythonpath` config — pass `env=` with explicit PYTHONPATH OR invoke via `subprocess.run([python, "-m", "kb.cli", ...])` from the repo root.

### 4. R3 adds genuine value for security-adjacent AC even after R1+R2 iterations

Cycle 7 went through 3 full review rounds. R1 caught 1 blocker + 5 majors. R2 (post-R1-fix) caught 2 residual issues. R3 (post-R2-fix) caught 2 more: the PYTHONPATH bug AND `{e}` leak sites in `browse.py` + `quality.py` that were outside my original AC12/13 scope. A 3-round review IS disproportionately valuable when the AC class is security (error-string leaks) because adjacent same-class modules naturally fall outside the literal AC scope but share the threat class.

**Action for Step 16 skill patch**:
- Strengthen the R3 rationale: for security-class AC (path leaks, injection, secrets), the review should explicitly ask "are there same-class leaks in ADJACENT modules I scoped out?". Not every cycle, but specifically for security AC.

### 5. Venv package tear-down during cycle — environmental warning

Mid-cycle (after my `.venv/Scripts/python -m pip install -e .` to recover kb), subsequent test runs started failing with `anthropic`, `fastmcp`, `pydantic` missing. Root cause not fully diagnosed — possibly a stale `pip install -e .` write interfering with `pydantic-core`'s RECORD file, possibly an unrelated env drift. Had to manually rm the broken pydantic_core dir + reinstall.

**Action**: not a skill patch — an environmental oddity. Record in memory as a thing to watch for, but no generalizable rule.

## Cleanup checklist

- [x] PR #21 merged to main at `2026-04-18T01:09:20Z`.
- [x] Local main fast-forwarded (`59e6e19..b3559d3`).
- [x] Branch `feat/backlog-by-file-cycle7` deleted.
- [x] Post-merge Dependabot alert count = 0 (no late-arrival CVEs).
- [x] Step-16 decisions doc written (this file).
- [ ] Feature-dev SKILL.md patched with 3 new lessons (next step).
- [ ] Step-16 decisions doc committed to main.

## Skill patch targets

The four SKILL.md amendments listed in Meta-lessons 1–4 above. Target file:
`C:\Users\Admin\.claude\skills\feature-dev\SKILL.md` (local, not in the repo).

The user's memory `feedback_cve_patch_before_docs.md` already codifies Meta-lesson 1 as a durable instruction. The skill patch is still worth applying so fresh instantiations that don't see the memory still run the correct order.
