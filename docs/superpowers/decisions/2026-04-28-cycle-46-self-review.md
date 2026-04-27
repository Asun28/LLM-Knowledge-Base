# Cycle 46 — Step 16 Self-Review + Skill Patches

**Date:** 2026-04-28
**Cycle scope:** Phase 4.6 LOW closeout (`lint/_augment_*.py` shim deletion deferred from cycle-44 → 45 → 46) + dep-CVE re-verification + BACKLOG hygiene + multi-site doc-sync
**Result:** PR #68 squash-merged at 2026-04-27 21:46:57Z as commit `cb9dca0` on `main`. 7 implementation commits + 1 R1-fix commit + this self-review = 9 total.
**Worktree:** `D:/Projects/llm-wiki-flywheel-c46` (created from main via `git worktree add` per C42-L4); cleaned up at Step 15.

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | mostly — Opus pre-decision corrected AC1 scope from 38/9 → 36/8; baseline test count 3025/243 not 3027/244 (CLAUDE.md drift discovered) | Opus subagent caught requirements-doc undercount via direct grep — pre-decision empirical verification works |
| 2 — Threat model + dep-CVE baseline | yes | yes | pip-audit baseline was 21089 bytes capturing 4 known carry-over vulns; same as cycle-41 |
| 3 — Brainstorming | SKIPPED | n/a | hygiene cycle (cycle-39/40/41/42 precedent) |
| 4 — Design eval | SKIPPED | n/a | trivial mechanical migration; Step 14 R1 dual-review covers dual-eyeball |
| 5 — Design decision gate | yes (Opus subagent) | yes — 13 questions resolved at HIGH confidence (Q2 MEDIUM cosmetic) + 7 binding CONDITIONS + 7 amendment notes | Opus 4.7's pre-decision empirical-verification block (corrected 4 claims via live-worktree greps) was extraordinary value — biggest single source of cycle-46's accuracy |
| 6 — Context7 | SKIPPED | n/a | no third-party libs |
| 7 — Implementation plan | yes (primary) | yes — 6 tasks → 6 commits | C37-L5 primary-session call was correct (12 ACs ≤ 15 threshold; primary holds full Steps 1-5 context) |
| 8 — Plan gate | yes (primary self-check per cycle-21 L1) | yes — APPROVE with 12/12 AC coverage + 5/5 T-item coverage + 7/7 CONDITION coverage table | self-verification matched the plan's claims |
| 9 — Implementation (TDD) | yes (primary, per task) | mostly — TASK 2 first Edit attempt failed because old_string used `kb.lint.augment.manifest` (the post-TASK-1 test reference path) instead of `kb.lint._augment_manifest` (manifest.py's own internal sys.modules.get key) | **C46-L2 candidate:** Edit old_string drift after upstream `replace_all=True` — the substring under edit was NOT in the test files (already migrated) but persisted in the src/ `_sync_legacy_shim()` function body which TASK 1's test-only replace_all didn't touch |
| 9.5 — Simplify | SKIPPED | n/a | <50 LoC src diff; signature-preserving deletion |
| 10 — CI hard gate | yes | mostly — first full pytest run had 1 flaky `test_persist_contradictions_concurrent` failure; passed on retry; ruff clean | flaky-test-on-retry pattern is documented in CHANGELOG-history — not a cycle-46 regression |
| 11 — Security verify + PR-CVE diff | yes (primary) | yes — T1 PR-introduced CVE diff = empty; T2-T5 all clean | dep-CVE postcheck = baseline (no introduced vulns) |
| 11.5 — Class A opportunistic | yes (primary) | yes — confirmed no-op (4 advisories no upstream patch; pip 26.1 advisory still null per `gh api graphql`) | conservative posture per cycle-22 L4 held |
| 12 — Doc update | yes (primary) | mostly — discovered 2-file CLAUDE.md/testing.md/implementation-status.md/README.md drift from cycle-45 (CLAUDE.md said 3027/244 instead of 3025/243; testing.md/implementation-status.md/README.md said 3019/241 instead of 3025/243) | **C46-L4 candidate:** cycle 45's doc-sync was incomplete — CI hotfix #67 deleted `test_cycle45_init_reexports_match_legacy_surface.py` without propagating the count delta to the 4 doc-sync sites |
| 13 — Branch finalise + PR | yes | yes — PR #68 opened cleanly with structured body |  |
| 14 — PR review (R1+R2+R3) | yes | mostly — R1 Codex caught 1 MAJOR (capital-C `Cycle-41` sites missed by lowercase-only replace_all); R1 DeepSeek had 1 false-positive NIT (ruff I001 — Step 10 already passed); R2 verified fix; R3 audit-doc drift APPROVE | **C46-L1 candidate:** case-sensitive `Edit replace_all=true` on text containing capital/lowercase variants — TASK 5's substring `cycle-41 re-confirmed 2026-04-27` only matched 2 of 5 sites; 3 capital-C `Cycle-41` sites survived |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes — squash-merge succeeded; worktree + branch cleaned; main venv editable kb pointer restored; 0 late-arrival alerts |  |
| 16 — Self-review (this) | yes | n/a | — |

## Patterns to PRESERVE

1. **Dedicated worktree per C42-L4 from-the-start.** `git worktree add ../llm-wiki-flywheel-c46 -b cycle-46-batch` at Step 1 (before any Edit). Eliminates parallel-cycle collisions.

2. **Opus subagent pre-decision empirical verification.** The Step 5 prompt explicitly asked Opus to grep the live worktree before scoring; Opus corrected 4 requirements-doc claims (AC1 patch-count, baseline test count, `import sys` removability, orchestrator.py docstring placement). Continue mandating this pattern in Step 5 prompts.

3. **Primary-session implementation for ≤15 ACs / ≤5 src files / primary-holds-context.** C37-L5 trigger held perfectly for cycle 46 (12 ACs, 3 src files modified + 2 deleted, primary held all context). 6 tasks completed in ~1 hour wall-clock at primary speed; Codex dispatch overhead would have added 10-20 minutes per task.

4. **TDD-via-test-first only when test failure stays in commit boundary.** TASK 3 batched AC2 (anchor refresh with failing assertions) + AC6+AC7 (delete shims that make assertions pass) into ONE commit because the branch must stay green per Step 10 hard gate "All pass or stop". Squash-merge collapses the commit-level shape anyway.

5. **R3 audit-doc drift always FIRST in prompt (cycle-19 L4).** Cycle 46 R3 prompt led with "AUDIT-DOC drift checks REQUIRED FIRST"; R3 Sonnet executed the audit-doc checks before code synthesis and reported them in a dedicated section. R3 caught zero drift — but the verification value comes from running the check, not finding hits.

6. **3-round PR review for AC ≥ 25 OR design-Q ≥ 10 (cycle-17 L4 d).** Cycle 46 had 12 ACs but 13 design Qs → R3 fired. R3 caught zero blockers but verified the cycle-45 ship-narrative reconstruction (independent verification of the 3027/244 → 3025/243 chain). Worth the dispatch overhead.

## Surprises that became skill patches

### C46-L1 — Case-sensitive `Edit replace_all=True` misses capital/lowercase variants

**Incident:** TASK 5 used `Edit replace_all=True` on the literal substring `cycle-41 re-confirmed 2026-04-27`. The diskcache (line 126) and ragas (line 129) entries used lowercase 'c'; the litellm (line 132), pip (line 135), and resolver-conflicts (line 158) entries used capital 'C' because `Cycle-41 re-confirmed 2026-04-27` started a parenthetical sentence in their cumulative-history surfaced-and-re-confirmed strings. R1 Codex caught all 3 capital-C survivors via direct file-grep at review time. R1 DeepSeek (full-diff inspection) MISSED them.

**Lesson (refines cycle-24 L1):** `Edit replace_all=True` on text-prose patterns where the substring can occur sentence-initial (capital-C) AND mid-sentence (lowercase-c) MUST run case-INSENSITIVE verification. After each `replace_all=True` Edit, verify with `grep -ciE 'pattern' file` (NOT `grep -c`); count must equal expected total across BOTH casings. Same applies to single-quote vs double-quote variants of the same string in source code, and to space-prefixed vs newline-prefixed identifiers.

**Self-check:** When constructing `Edit replace_all=true` on a phrase that could appear both sentence-initial and mid-sentence, run TWO Edit calls (one for capital-letter form, one for lowercase form) — OR use the `-i` flag in your verification grep. Concrete: `git diff --check` before commit + `grep -ciE 'old_pattern' <files> | sort -u` returning zero hits.

**Prevention rule for future cycles:** TASK 5 / Step 12 doc-sync prompts should include: "For BACKLOG.md or CHANGELOG.md prose substring updates, generate BOTH the `Pattern` (capital-leading) and `pattern` (lowercase-leading) Edit pairs, since parenthetical phrase starts capitalize the leading letter."

### C46-L2 — Edit old_string drift after upstream `replace_all=True` in same session

**Incident:** TASK 2's first Edit attempt to delete `_sync_legacy_shim()` from `manifest.py` used `old_string` containing `kb.lint.augment.manifest` because that's how I'd been thinking about the migrated path. But manifest.py's own `_sync_legacy_shim()` body referenced `kb.lint._augment_manifest` (the legacy shim it was mirroring TO, not FROM). The Edit failed with "String to replace not found in file." Reading the file showed `kb.lint._augment_manifest` was the actual content. TASK 1's test-only `replace_all=True` had not touched manifest.py because manifest.py wasn't in TASK 1's file list.

**Lesson (refines cycle-24 L1 + new dimension):** When constructing Edit `old_string` for a file that was NOT in a prior `replace_all=True` pass, do NOT assume the prior pass's substring transformation applied. The `_sync_legacy_shim()` function in manifest.py and rate.py was specifically the cycle-44 mirror mechanism that READ from one path and WROTE to another — both directions exist in source-of-truth code, so substring assumptions break.

**Self-check:** Before each Edit, briefly Read the target lines (offset/limit small range) to confirm the actual current content. The Read prerequisite has dual purpose: (a) Edit-tool compliance, (b) verify the substring still exists with the assumed casing/path/etc. The cost is one Read; the saved cost is a failed Edit + retry cycle.

**Refines cycle-24 L1:** old_string drift can fire even when the pattern is single-line literal — if a parallel `replace_all=True` pass touched related but-not-identical files, the source-of-truth content may differ from the operator's mental model.

### C46-L3 — Worktree venv setup against a project with documented resolver conflicts

**Incident:** Standard cycle-44/45 worktree setup recipe is `python -m venv <c46>/.venv && pip install -r requirements.txt -e .`. This FAILED for cycle 46 with `ResolutionImpossible: arxiv 2.4.1 depends on requests~=2.32.0` — exactly the cycle-22 L1 lesson, but now firing at venv-create time instead of pip-audit time. The pre-existing resolver conflicts (cycle-34 AC52: arxiv/requests, crawl4ai/lxml, instructor/rich) blocked a fresh `pip install`.

**Workaround:** From the main repo's `.venv`, repoint the editable kb install to the cycle-46 worktree via `pip install --no-deps -e D:/Projects/llm-wiki-flywheel-c46/`. This reuses main's transitive deps and overrides the editable kb pointer. After Step 15 cleanup: `pip install --no-deps -e D:/Projects/llm-wiki-flywheel/` to restore.

**Lesson (refines C42-L4):** Worktree venv setup pattern depends on the project's resolver state. For projects with documented resolver conflicts that block `pip install -r requirements.txt`, USE the editable-repoint pattern instead of fresh venv creation. The trade-off: main's venv is "tainted" with the worktree pointer for the cycle's duration, so parallel cycle attempts in main worktree would import from c46/. User-explicit no-parallel-cycles state required.

**Concrete recipe:**
```bash
# Setup (Step 1):
git worktree add ../<repo>-c<N> -b cycle-<N>-batch
# Skip: python -m venv ../<repo>-c<N>/.venv  (will fail on resolver conflicts)
# Instead: repoint main's editable kb
<main>/.venv/Scripts/pip.exe install --no-deps -e ../<repo>-c<N>/
# Verify:
<main>/.venv/Scripts/python.exe -c "import kb; print(kb.__file__)"  # should show c<N> path
# All subsequent pytest/ruff runs from c<N>/ via main's python.

# Cleanup (Step 15):
<main>/.venv/Scripts/pip.exe install --no-deps -e ../<repo>/  # restore main pointer
git worktree remove ../<repo>-c<N> --force
git branch -D cycle-<N>-batch
```

**Prevention rule for future cycles:** Document this pattern as the default for cycles in repos with resolver-conflict carry-overs (cycle-34 AC52 carry-over still alive in cycle 46). When the resolver conflicts are resolved upstream, the standard fresh-venv pattern can return.

### C46-L4 — Cycle-45 doc-sync was incomplete; cycle-46 caught the 4-site drift

**Incident:** Cycle 45 self-review at `2026-04-27-cycle-45-self-review.md` claimed test-count baseline 3027/244 (cycle-45 ship state). Cycle-45 CI hotfix PR #67 deleted `tests/test_cycle45_init_reexports_match_legacy_surface.py` (1 file, 2 parametrized tests) → actual main state was 3025/243. CLAUDE.md got the cycle-45 ship update (3027/244) but NOT the CI hotfix delta. testing.md / implementation-status.md / README.md MISSED both updates and stayed at cycle-44 state (3019/241). 4-site drift went undetected for 1 cycle.

**Lesson (refines C26-L2 + C39-L3 + cycle-15 L4):** When a cycle ships AND has a CI hotfix between the ship-PR and the next cycle's start, the hotfix MUST propagate doc-sync updates. Cycle 45 didn't do this. Cycle 46 picked up the slack at TASK 6.

**Prevention rule for future cycles:**
1. Every CI hotfix PR (e.g., #67 in cycle 45) MUST include doc-sync updates if the hotfix changes test count or file count. Add to the CI hotfix PR template: "If this hotfix deletes/adds test files, update CLAUDE.md / docs/reference/testing.md / docs/reference/implementation-status.md / README.md test-count narrative."
2. Step 16 self-review for the cycle that ships the hotfix MUST verify all 4 doc-sync sites match the post-hotfix state. Add a checklist row: "All 4 doc-sync sites at post-hotfix count? (CLAUDE.md / testing.md / implementation-status.md / README.md)".
3. The next cycle's Step 1 requirements doc should `pytest --collect-only | tail -1` AND grep all 4 sites — discrepancy is a baseline-fix scope item before any new ACs are added.

### C46-L5 — Codex direct-grep beats DeepSeek diff-inspection for case-sensitive substring audits

**Incident:** R1 DeepSeek had FULL diff context (179KB) and reviewed it carefully but missed the 3 capital-C `Cycle-41` BACKLOG entries because diff-context emphasizes line-level changes, not pattern-occurrence audits. R1 Codex (agent dispatch) used `grep` on the actual file and caught all 3.

**Lesson (refines C40-L1):** R1 review prompts should explicitly ask reviewers to RUN GREP on the actual files for pattern-completeness audits, not infer from diff inspection alone. The diff-only approach is great for "what changed?" but bad for "what should have changed but didn't?". Cycle 46 example: TASK 5 INTENDED to bump 5 cycle-41 timestamps; the diff showed 5 line-level edits; only 2 of them were the SUBSTRING `cycle-41 re-confirmed`, the other 3 were neighbouring narrative lines that didn't change. A grep on `[Cc]ycle-?41 re-confirmed` against the file would have shown 3 unchanged sites. The reviewer who runs grep catches what the diff-only reviewer misses.

**Prevention rule for future cycles:** R1 prompts (both DeepSeek and Codex) should include a mandatory check: "For any AC claim of the form 'bumped N timestamps' or 'updated N references', run grep on the post-cycle file state and verify the actual count equals N. If diff-context shows fewer changes than the AC claims, investigate the discrepancy as either AC-narrative drift OR untouched sites that should have been touched."

## Final scorecard summary

- 16/16 steps executed (Steps 3, 4, 6, 9.5 SKIPPED per skip-eligibility rules; all four skips justified per C37-L5 / cycle-39+ precedent).
- 1 R1 MAJOR caught + fixed in-cycle (case-sensitive substring miss; 3 sites).
- 0 R2 / R3 blockers.
- Zero PR-introduced CVEs.
- Zero new CI dimensions per cycle-36 L1 (windows-latest matrix, GHA-Windows multiprocessing, TestWriteItemFiles POSIX all re-deferred to cycle-47+).
- 5 skill-patch candidates (C46-L1 through C46-L5) — each refines a prior lesson rather than introducing a wholly new pattern, indicating the skill is mature.

**Cycle 46 closes Phase 4.6 entirely.** All Phase 4.6 MEDIUM (M1+M2+M3+M4) and LOW (L1+L2+L4+L5) items resolved across cycles 42 + 44 + 45 + 46. The DeepSeek V4 Pro full-repo audit findings have been fully closed.

## Operator follow-up (skill infrastructure integration)

Per cycle-39 L5: skill patches that fix infrastructure (CLI wrappers, env defaults like `~/.claude/bin/deepseek-cli.py`) ship in user-global `~/.claude/` directory NOT project repo. The 5 cycle-46 lessons (C46-L1 through C46-L5) belong in `~/.claude/skills/dev_ds/references/cycle-lessons.md` (per the dev_ds SKILL.md "Accumulated rules index" pattern):

1. **Add C46-L1 entry** under "Test authoring — ensure a production revert fails the test" or new "Edit hygiene" section: `- C46-L1 — case-sensitive Edit replace_all=True misses capital/lowercase variants; use grep -ciE for verification (refines cycle-24 L1)`.
2. **Add C46-L2 entry** under "Implementation gotchas": `- C46-L2 — Edit old_string drift after upstream replace_all=True in same session; Read each target before Edit (refines cycle-24 L1)`.
3. **Add C46-L3 entry** under "Subagent dispatch and fallback" or new "Worktree setup" section: `- C46-L3 — worktree venv setup pattern in repos with resolver conflicts; use pip install --no-deps -e <c-N>/ from main venv (refines C42-L4 + cycle-22 L1)`.
4. **Add C46-L4 entry** under "Docs and count drift": `- C46-L4 — CI hotfix PRs MUST propagate doc-sync updates; cycle-N+1 self-review verifies post-hotfix state across 4 sites (refines C26-L2 + C39-L3 + cycle-15 L4)`.
5. **Add C46-L5 entry** under "Subagent dispatch and fallback": `- C46-L5 — R1 reviewers must run grep on actual files for pattern-completeness audits, not infer from diff inspection (refines C40-L1)`.

The full lesson text for each goes into `~/.claude/skills/dev_ds/references/cycle-lessons.md` under a new `## Cycle 46 skill patches (2026-04-28)` heading. This project repo's self-review doc is the audit trail; the user-global skill infrastructure stores the executable patterns.

## Cycle 46 metrics

| Metric | Value |
|---|---|
| Total ACs | 12 |
| Design questions resolved | 13 (HIGH × 12 + MEDIUM × 1) |
| Binding CONDITIONS | 7 |
| Implementation tasks | 6 |
| Implementation commits | 6 |
| Doc-update commits | 1 (TASK 6 bundled with implementation) |
| R1-fix commits | 1 (Codex MAJOR 1) |
| Self-review commits | 1 (this) |
| Total commits on cycle-46-batch | 7 (squash-merged to 1 on main) |
| Test count delta | 3025 → 3025 (net 0; -1 AC2 deletion + 1 AC2 addition) |
| File count delta | -2 src (shim deletions); -0 tests; net -2 |
| LOC delta | ~+1130 / ~-200 (mostly decision docs +1110; src -75) |
| Steps executed | 12 (Steps 1, 2, 5, 7, 8, 9, 10, 11, 11.5, 12, 13, 14, 15, 16) |
| Steps skipped | 4 (Steps 3, 4, 6, 9.5) |
| PR-introduced CVEs | 0 |
| Late-arrival CVEs (post-merge diff) | 0 |
| New CI dimensions (cycle-36 L1) | 0 |
| Skill-patch candidates | 5 (C46-L1 through C46-L5) |
