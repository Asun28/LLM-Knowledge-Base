# Cycle 15 — Brainstorm (3 approaches)

**Date:** 2026-04-20
**Context:** 32 ACs wiring cycle-14 helpers (`decay_days_for`, `tier1_budget_for`, `save_page_frontmatter`, publish builders) into call sites + new small features (`volatility_multiplier_for`, two new lint checks, publish atomic writes + incremental skip, `authored_by` consumers).
**Step-2 inputs:** 10 threat items with 8 AC amendments. Zero new deps. Dependabot 0 alerts.

## Approach A — Direct wiring + new checks (RECOMMENDED)

**Shape.** Each AC is either (a) a flat-constant → helper-call substitution at an existing line, or (b) a new function adjacent to an existing pattern (new `_apply_authored_by_boost` next to `_apply_status_boost`; new `check_status_mature_stale` next to `check_staleness`). Volatility multiplier ships as a 30-line helper + dict in config.py. Publish atomic writes reuse the existing `atomic_text_write` helper from `kb.utils.io`. Incremental skip is a ~15-line branch at the top of each builder.

**Code footprint.** ~450 LoC of source + ~700 LoC of tests (13 new `test_cycle15_*.py` files mirroring cycle-14 layout). No new modules, no new MCP tools, no new CLI subcommands (only a flag on existing `kb publish`).

**Review risk.** Low. Every AC follows an existing cycle-14 pattern (`_apply_status_boost` → `_apply_authored_by_boost`, AC23 status key → AC18/19 authored_by/belief_state keys, cycle-14 T2 epistemic filter inside builders → cycle-15 T10c preserves filter before skip). Step-5 gate resolves the 8 threat-model amendments into the final AC text. Step-9 inline-in-primary per cycle-13 L2 heuristic (< 30 LoC per task, mechanical migration, no novel APIs).

**Trade-offs.**
- **Pro:** predictable; each task < 5 min implementation + 5 min test; matches `feedback_batch_by_file` memory.
- **Pro:** preserves cycle-14 L3 loader-atomicity lesson by adding both `authored_by` and `belief_state` in the SAME cycle (not piecemeal).
- **Con:** adds 2 new lint check types to `run_all_checks`, so lint runs gain ~2ms per page (tolerable on 10k pages).
- **Con:** `volatility_multiplier_for` is a new public helper — future contributors may abuse its topic-keyword list.

## Approach B — Feature-flag new checks / consumers

**Shape.** Same as A, but gate AC5 (`check_status_mature_stale`), AC6 (`check_authored_by_drift`), AC3 (`_apply_authored_by_boost`), and AC8 (evolve seed-priority) behind env flags (`KB_ENABLE_CYCLE15_CHECKS` default off). Ship the code but don't enable it by default.

**Trade-offs.**
- **Pro:** safer rollout — operators opt in.
- **Con:** adds 4 env flags that must eventually be removed in a cycle-16 cleanup. Permanent config debt.
- **Con:** new lint checks are WARNING-level, not ERROR — blast radius is already bounded; a flag adds noise without reducing risk.

**Rejected.** Flag-guarding WARNING-level checks is over-engineering. New lint output is additive and ignorable; `_apply_authored_by_boost` is +2% (negligible on query ranking); seed-priority is stable-sort ordering (no user-visible disruption).

## Approach C — Roll into single migration refactor

**Shape.** Extract a `ConsumerContext` struct threading `decay_days_for(topics=…)`, `tier1_budget_for(component=…)`, `_apply_X_boost` through the query / lint / evolve pipelines in one architectural refactor. Future per-topic boosts land in one dataclass.

**Trade-offs.**
- **Pro:** one seam for all future per-topic / per-platform signal work.
- **Con:** turns 32 ACs into 100+; requires redesigning how `search_pages` / `check_all` / `suggest_new_pages` compose signals.
- **Con:** violates `feedback_batch_by_file` — batch cycles are mechanical; architectural refactors need their own design cycle.

**Rejected.** Scope explosion. Approach A keeps the 32-AC batch shape; Approach C needs a Phase-5 architectural design cycle.

## Decision

**Approach A.** Confirmed by:

1. Matches the cycle-13/cycle-14 batch-by-file shape (operator has full context from Step 1 + Step 2 per cycle-14 L1 heuristic).
2. Every AC < 30 LoC mechanical per cycle-13 L2 heuristic — implement in primary session.
3. Threat-model amendments resolve cleanly at Step 5 without architectural surgery.
4. Cycle-14 L3 atomicity rule honoured — `authored_by` + `belief_state` both land in `load_all_pages` this cycle.

**Open questions for Step-5 decision gate:**
- Q1: Should AC3 (`_apply_authored_by_boost`) and AC8 (evolve seed-priority) ship with the validate_frontmatter gate pattern from cycle-14 T9, or a lighter gate? (Threat-model recommends the full gate per T7.)
- Q2: Should AC12 incremental-publish be default-ON (skip-if-unchanged on `kb publish`) or default-OFF (explicit `--incremental`)? (Threat-model T10c recommends explicit first-run `--no-incremental` after upgrade.)
- Q3: Should AC17 use `load_page_frontmatter.cache_clear()` (process-wide, simple, threat-model T6) or a targeted invalidation (keyed removal, complex, lower blast radius)?
- Q4: Should AC16 clamp at `SOURCE_DECAY_DEFAULT_DAYS * 50` (~12 years) or a lower ceiling (threat-model T2)?
- Q5: Should AC6 regex anchor be `^## Evidence Trail` (cycle-14 sentinel) or `## Evidence Trail` (body-anywhere)? (Threat-model T5 recommends the sentinel anchor.)
- Q6: Should AC7 wire both new checks into `run_all_checks` unconditionally, or add a `--checks=cycle15` include flag? (Approach A: unconditional; flag would be Approach B-lite.)
- Q7: Should AC18/AC19 `load_all_pages` additive-keys fix be applied retroactively to the cycle-14 `status` field's docstring to document the pattern? (Zero behaviour change, doc-only.)
- Q8: Should `SOURCE_VOLATILITY_TOPICS` be tuple-of-strings or dict-of-multiplier? AC14 says dict; alternative is single-multiplier list (all volatile topics share 1.1). Dict preserves future per-topic tuning.

All 8 resolve at Step 5 via Opus decision gate.
