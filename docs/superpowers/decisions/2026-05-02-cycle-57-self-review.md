# Cycle 57 — Step 24 Self-Review + Skill Patch

**Date:** 2026-05-02
**PR:** #80 — `cycle 57 — Freeze-and-fold (5-fold batch) + sentinel-DELETE for test_embedding_dim_resolved`
**Merge commit:** `cdd94bd`
**Trial slot:** 3rd `dev-mimo-opus` cycle (after cycles 55 + 56)

---

## Scorecard (Steps 1 → 23)

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 01 Requirements + ACs | yes | yes | — |
| 02 Threat model + dep-CVE baseline | yes | yes | `python -m pip-audit` failed with `No module named pip-audit` (per C35-L1: pip-audit binary, not module). Used the binary; baseline captured cleanly. |
| 03 Brainstorming | skipped (trivial fold pattern) | n/a | — |
| 04 Design eval (R1 inline; R2 skipped) | yes | yes | Detected vacuous-OR clause in `TestKbQueryMaxResultsForwarding::test_max_results_forwarded_in_api_mode`; preserved verbatim per host-shape rule + noted in T1 commit message as future-cycle upgrade candidate. |
| 05 Decision gate | yes | yes | All 4 questions resolved inline per cycle-21 L1; zero ESCALATE. |
| 06 Context7 | skipped (pure stdlib) | n/a | — |
| 07 Implementation plan | yes | yes | — |
| 08 Plan gate | yes | yes | APPROVE; no PLAN-AMENDS-DESIGN. |
| 09a-f Implementation (6 ACs) | yes | yes | T1 receiver pytest 47→57 ✓, T2 23→27 ✓, T3 21→29 ✓, T4 67→75 ✓, T5 53→60 ✓, T6 27→26 (sentinel deletion) ✓. AC4 hit `# noqa: E402` ruff requirement on appended-section imports — applied + ruff format added trailing newline to test_utils.py per W292. |
| 10 Simplify | skipped (no `src/` diff) | n/a | — |
| 11 SAST + secrets | skipped (no `src/kb/` diff) | n/a | — |
| 12 CI hard gate | yes | yes | Local Windows pytest 3010 passed + 11 skipped + 0 errors in 142.70s; ruff format + ruff check both clean. |
| 13 Coverage delta | skipped (test-fold cycle judged against receivers per skill skip-when) | n/a | — |
| 14 Security verify | skipped (Step 2 had no threat-model items requiring code-side verification) | n/a | — |
| 15 Existing-CVE patch | skipped (no fix-versions newly available; same 4 unresolved as cycle 56) | n/a | — |
| 16 IaC + container scan + SBOM | skipped (no `*.tf`/`Dockerfile`/dep-manifest changes) | n/a | — |
| 17 Doc update | yes | yes | CHANGELOG, CHANGELOG-history, CLAUDE.md, README, docs/reference/{testing,implementation-status}.md, BACKLOG.md. AC6 sentinel deletion CLOSED a cycle-56+ BACKLOG marker (deleted from BACKLOG, brief in CHANGELOG, detail in CHANGELOG-history). |
| 18 Branch finalise + PR | yes | yes | PR #80 created cleanly. |
| 19 Signed commits | skipped (repo policy + no published artifact) | n/a | — |
| 20 PR review | yes (R1 inline, R2 skipped) | yes | Per cycle-37 L5 primary-session default for ≤15 ACs / ≤5 src files / primary-holds-context — fold-only cycle qualifies. R1 inline verdict APPROVE. |
| 21 Merge + cleanup | yes | yes | Merged at cdd94bd. Worktree removed; branches deleted. |
| 22 Deploy gate | skipped (no deployable artifact) | n/a | — |
| 23 Smoke check | skipped (Step 22 was skipped) | n/a | — |

**Clean rows:** 1, 5, 7, 8, 9 (all 6 sub-tasks), 12, 17, 18, 20, 21 — every step executed first-try. Zero re-dispatches; zero rejected gates.

---

## Surprises requiring lesson capture

**Two surprises rose above the threshold of "trivial fold mechanics":**

### S1 — `EMBEDDING_DIM` was already gone from `src/kb`

The cycle-56+ BACKLOG entry for `test_review.py::test_embedding_dim_resolved` was filed by cycle-55 R1 Sonnet on the assumption that `EMBEDDING_DIM` still existed in `kb.config` and `kb.query.embeddings.VectorIndex`. The BACKLOG entry's option (1) said: "delete `EMBEDDING_DIM` from `kb.config` if truly unused (`grep -rnE EMBEDDING_DIM src/kb` returns config + VectorIndex.build only) and remove the test."

But `grep -rnE "EMBEDDING_DIM" src/kb` returned **zero** hits at cycle 57. CHANGELOG-history.md line 2214 records the original removal: "`kb.config` gains `WIKI_CONTRADICTIONS` path constant and `MAX_QUESTION_LEN = 2000`; **removes unused `EMBEDDING_DIM`**."

**Lesson:** When a BACKLOG entry's option-(1) precondition is "if X is truly unused, delete X and the test", the option may have **already been satisfied silently** by an unrelated upstream cleanup commit. The next cycle picking up the marker has to re-grep BEFORE choosing the upgrade path — option (2) (replacement behavioral pin) becomes infeasible if the production constant no longer exists.

This is a refinement of cycle-3 R1 Opus L (see Red Flags row "BACKLOG.md says this item is open — write the test and fix it"): **same shape applies to "design refers to a constant that another cycle has already deleted."** The fix is to grep for the cited symbol BEFORE choosing the upgrade option.

→ **C57-L1.** Filing as cycle-lessons.md entry.

### S2 — `# noqa: E402` is the right hygiene for appended-fold-section imports

When AC4 appended a new section at the EOF of `test_v070.py` containing module-level imports (`import ast as _cycle17_ast` etc.), ruff flagged E402 ("Module level import not at top of file"). Three options:

1. Move imports to top of file (loses cohesion of fold-section).
2. Move imports inside the helper function (works for `ast`, but `sys` and `Path` are used by class methods AND module-level constants `_CYCLE17_REPO_ROOT` / `_CYCLE17_SRC_KB_MCP` — function-local won't reach them).
3. Add `# noqa: E402` to the appended imports.

I chose option (3). This is consistent with the existing fold convention: cycle-49+50+51+52 all appended sections to `test_v070.py` without ruff E402 violations because their fold sections didn't introduce NEW module-level imports — they reused what was already at the top OR went function-local.

**Lesson:** When a fold introduces module-level imports that THE RECEIVER doesn't already have, the cleanest hygiene is `# noqa: E402` on the appended imports with a one-line comment ("appended fold section per cycle-49+50+51 host-shape"). This preserves cohesion without restructuring the receiver. Function-local imports don't work when class methods AND module-level constants both need the symbol.

This is a refinement of cycle-19 L2 (reload-leak avoidance via function-local imports): **the rule is "function-local where possible", but when module-level constants depend on the import, use `# noqa: E402` instead of restructuring the receiver.**

→ **C57-L2.** Filing as cycle-lessons.md entry.

---

## Skill patches

### C57-L1 — Re-grep BACKLOG-cited symbols before picking up the marker

**Rule.** When a BACKLOG entry mentions a specific code symbol (`EMBEDDING_DIM`, `_pure_helper`, `_validate_X`) and proposes options conditional on its current state ("if X is unused, delete it"), grep `src/kb` for that symbol BEFORE choosing the option. The symbol may have been removed by an unrelated upstream cleanup.

**Why:** Cycle 57 AC6 picked up the cycle-56+ marker for `test_embedding_dim_resolved` and discovered `EMBEDDING_DIM` was ALREADY removed from `src/kb`. The cycle-56+ BACKLOG entry's option (2) ("replace getsource grep with a real validation pin") had become infeasible — option (1) (delete the test) was the only viable path, and it was the simpler choice anyway.

**How to apply:** At Step 1 (requirements), for every BACKLOG entry being picked up that names a specific code symbol or constant, run `grep -rnE "<symbol>" src/kb` and `grep -rnE "<symbol>" tests/` to confirm current state. If the symbol is gone, narrow the AC to "delete the now-vacuous test" without spending design-cycle time on the more complex replacement-pin path.

**Refines:** cycle-3 R1 Opus Red Flag ("BACKLOG.md says this item is open — write the test and fix it") — extends from "verify against current source before writing a test for it" to "verify against current source before choosing between BACKLOG options, since options conditional on symbol state may have ALREADY been satisfied by an unrelated commit."

### C57-L2 — `# noqa: E402` for appended-fold-section module-level imports

**Rule.** When a fold appends a new section at EOF of a receiver test file and that section requires module-level imports the receiver doesn't already have at the top, add `# noqa: E402` to the appended imports with a one-line comment ("appended fold section per cycle-N+M host-shape"). Do not restructure the receiver to move the imports to the top — that would break cohesion of the fold section.

**Why:** Cycle 57 AC4 folded `test_cycle17_lazy_imports.py` (which has module-level `import ast` / `import sys` / `from pathlib import Path` for AST-walking) into `test_v070.py`. The receiver had none of these at the top. Function-local imports don't work because module-level constants `_CYCLE17_REPO_ROOT = _Cycle17Path(__file__).resolve().parent.parent` need `Path` at import time. `# noqa: E402` with disambiguation comment preserved cohesion without polluting the receiver's top imports with fold-specific symbols.

**How to apply:** At Step 9 (implementation), when appending a new section to a receiver test file, check if the source's module-level imports already exist at the top of the receiver. If yes, omit them from the appended section. If no, decide:
1. Are the imports needed by class methods AND module-level constants? → `# noqa: E402` on appended imports (cleanest).
2. Are they needed only inside method bodies? → Move to function-local per cycle-19 L2 reload-leak avoidance.
3. Are they trivial (e.g. `import json` used in 1 method)? → Function-local for hygiene.

**Refines:** cycle-19 L2 (reload-leak avoidance via function-local imports) — extends from "function-local where possible" to "function-local where the symbol is used only inside function bodies; `# noqa: E402` on appended section when module-level constants depend on the import."

---

## MiMo trial telemetry — cycle 57 data point

| Aspect | Cycle 57 outcome |
|--------|------------------|
| Cycle slot in May 2026 trial | 3rd (after cycles 55 + 56) |
| Steps that ran in primary session | All 6 implementation tasks + Steps 1-8 + Step 12 + Step 17 + Step 18 + Step 20 + Step 21 |
| Steps that dispatched to sub-agents | None |
| `mimocoding-rescue` calls | 0 |
| `mimochat-rescue` calls | 0 |
| `deepseek-rescue` calls | 0 |
| `codex:codex-rescue` calls | 0 |
| Token Plan burn | 0 |
| Identity-confusion incidents | 0 |
| Step 14 misses that Step 9 should have caught | n/a (Steps 14 + 9 both clean) |
| Wall-clock time (rough) | ~25 min (single Opus 4.7 session, no dispatch overhead) |

**C37-L5 confirmed for the third time.** Small mechanical folds (≤6 ACs, ≤5 src files, primary-holds-context) belong in primary session — dispatch overhead dominates the value of a second model. Cycle 55 had 4 folds dispatched + 1 in primary; cycle 56 had 3 dispatched + 3 primary; cycle 57 had 0 dispatched + 6 primary. The trend is toward primary-session-default for the entire fold cadence.

**Implication for the 2026-05-31 trial writeup:** for hygiene cycles (Phase 4.5 HIGH #4 freeze-and-fold), the MiMo dispatch path adds latency without quality benefit. Reserve MiMo for genuine parallelism (≥4 independent tasks) or unfamiliar-territory cycles. Continue using DeepSeek+Codex+Sonnet diversity at Step 20 for security-class cycles.

---

## Closing

Cycle 57 closes cleanly. PR #80 merged at `cdd94bd`. Two new lesson entries (C57-L1, C57-L2) being added to `references/cycle-lessons.md` and indexed under "Accumulated rules index" in the dev-mimo-opus skill spec. No follow-up work; no recurring monitor warranted.

Counts at merge: 3021 tests / 208 files (3010 passed + 11 skipped Windows local). Subject to future rebases as cycle-53 and cycle-54 land.
