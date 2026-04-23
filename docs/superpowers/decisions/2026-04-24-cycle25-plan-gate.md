# Cycle 25 — Plan Gate (Step 8)

**Verdict: REJECT.**

1. **AC7 is not fully covered by TASK 3.** The decided design requires `logger.warning("compile_wiki: stale in_progress:%s marker for %s", hash, source)` for each stale `in_progress:` entry, naming each source path. TASK 3 instead plans one aggregate warning with `", ".join(stale_markers[:10])`, which silently omits source paths after the first 10 and does not assert per-entry warnings. Add either per-marker warning implementation or an explicit test asserting all stale marker source paths are named.

2. **CONDITION 11 is not mapped to an explicit implementation note or test assertion.** Design condition 11 requires `CLAUDE.md` to state that concurrent `kb compile` invocations may emit spurious `stale in_progress:` warnings and that this is expected and non-destructive. TASK 4's `CLAUDE.md` section covers the dim-mismatch counter and three-state manifest value-space, but does not explicitly include the concurrent-compile warning note.

3. **TASK 4 lacks an explicit verification expectation for AC10 / CONDITION 8.** The task says to delete the BACKLOG `.tmp awareness` entry and update changelogs in the same commit, but it does not name a concrete check such as grepping that the resolved BACKLOG entry is gone and that `CHANGELOG.md` / `CHANGELOG-history.md` contain the cycle-25 entry. Add these checks so every task has clear test or verification expectations.

Threat coverage is otherwise adequate: T1 maps to TASK 2, T2/T3 to TASK 3, T4/T5 to TASK 1, and T6 to TASK 4. Most ACs and conditions are covered substantively despite minor condition-number drift, but the gaps above block approval.
