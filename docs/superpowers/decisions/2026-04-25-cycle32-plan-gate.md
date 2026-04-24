# Cycle 32 — Step 8 Plan Gate (Primary-Session Self-Review)

**Date:** 2026-04-25 · **Method:** Primary-session inline self-review per cycle-21 L1 + cycle-22 L2 (Codex dispatch `a291e6f8edb9ae389` stopped after 8+ min hang).

**Fallback rationale:** The plan was authored in primary session (cycle-14 L1) with full Step 1-6 context and all 14 symbols grep-verified at Step 4. Gaps, if any, would be documentation/design clarifications — not code-exploration gaps. Primary-session self-review is the appropriate fallback per cycle-21 L1.

## Coverage matrix (AC → TASK)

| AC | TASK | Coverage |
|----|------|----------|
| AC1 (`kb compile-scan`) | TASK 3 | COVERED — thin wrapper via function-local import |
| AC2 (AC1 test coverage) | TASK 3 | COVERED — 3-test class (help + body-spy + error-path) |
| AC3 (`"Error["` widening) | TASK 1 | COVERED — tuple edit + docstring + 3 unit tests + 1 integration (in TASK 4) |
| AC4 (`kb ingest-content`) | TASK 4 | COVERED — thin wrapper with stat guard |
| AC5 (AC4 test coverage) | TASK 4 | COVERED — 5 tests including --use-api forwarding + Error[partial] integration |
| AC6 (fair-queue counter) | TASK 2 | COVERED — module-level int + stagger + underflow warning |
| AC7 (AC6 regression test) | TASK 2 | COVERED — threading.Barrier N=3 + 10 trials + counter-symmetry test |
| AC8 (doc sync) | Step 12 | DEFERRED to Step 12 (Codex doc subagent) per skill spec |

## Threat coverage (T → TASK/Step)

| T | Mitigation TASK | Coverage |
|---|-----------------|----------|
| T1 (content-file traversal) | Accepted by design | OPERATOR-CONTROLLED — documented in T1 threat model, no runtime enforcement per requirements non-goals |
| T2 (extraction-json DoS) | TASK 4 (C13 stat guard) | COVERED — `os.fstat` + `MAX_INGEST_CONTENT_CHARS` cap before read |
| T3 (URL YAML injection) | TASK 4 (C7 raw forward) | COVERED — CLI passes `url` verbatim; MCP `yaml_escape` unchanged |
| T4 (AC3 false positive on legit output) | TASK 1 (C2 peer scan) | COVERED — same-class peer scan confirms zero legitimate non-error emitters |
| T5 (revert-tolerant AC3 test) | TASK 1 + TASK 4 (C1) | COVERED — integration test via CLI spy is revert-divergent |
| T6 (counter drift) | TASK 2 (C3 + C14) | COVERED — outermost try/finally + logger.warning on underflow |
| T7 (stagger × backoff double-compound) | TASK 2 (C11 clamp) | COVERED — `min(position * STAGGER_MS / 1000, LOCK_POLL_INTERVAL)` |
| T8 (fair-queue overselling) | Step 12 (C8 language) | DEFERRED to doc update — CLAUDE.md uses "mitigation" + "intra-process only" |
| T9 (--wiki-dir UX) | TASK 3 (C9) | COVERED — "default: incremental" in help text; AC2 test |
| T10 (counter overflow) | TASK 2 (T7 clamp neutralises) | COVERED transitively via C11 |
| T11 (Error[partial]: leaks abs path) | Step 12 (C12 BACKLOG entry) | DEFERRED — filed in BACKLOG for future cycle per C12 |
| T12 (content-file large read) | TASK 4 (C13 stat guard) | COVERED — same mechanism as T2 |

## CONDITION coverage (C → test/grep target)

| C | TASK/Step | Test or Grep |
|---|-----------|--------------|
| C1 | TASK 1 + TASK 4 | `rg 'Error\[partial\]' tests/test_cycle32_*.py` ≥2 |
| C2 | Step 11 | `rg 'Error\[' src/kb/` returns exactly 6 known emitters |
| C3 | TASK 2 | counter-symmetry test + grep `_LOCK_WAITERS` in ONE try/finally |
| C4 | Step 6 DONE | Context7 queried + recorded (cycle32-context7.md) |
| C5 | Step 11 | `rg 'file_lock\(' src/kb/` count unchanged pre/post |
| C6 | TASK 2 | `rg 'threading\.Barrier' tests/test_cycle32_*.py` ≥1 |
| C7 | TASK 4 | `rg -n 'json\.loads\|url\.strip' src/kb/cli.py` no new matches in ingest_content body |
| C8 | Step 12 | CLAUDE.md language discipline grep |
| C9 | TASK 3 | "default: incremental" in help text |
| C10 | TASK 2 | `rg '^_LOCK_WAITERS' src/kb/utils/io.py` shows both decls |
| C11 | TASK 2 | `rg 'min\(.*_FAIR_QUEUE_STAGGER' src/kb/utils/io.py` ≥1 |
| C12 | Step 12 | BACKLOG MEDIUM entry for T11 |
| C13 | TASK 4 | `rg 'fstat\|st_size' src/kb/cli.py` shows stat guards |
| C14 | TASK 2 | `rg '_LOCK_WAITERS underflow' src/kb/utils/io.py` ≥1 |
| C15 | TASK 4 | `rg 'use_api=True' tests/test_cycle32_*.py` ≥1 |
| C16 | Step 12 | BACKLOG.md:125-126 fair-queue entry DELETED |

## Gaps

None. Plan is well-formed; all ACs, threats, and conditions map to TASK-or-Step coverage. No code-exploration gaps identified.

## Verdict

**APPROVE** — plan passes primary-session self-review. Proceed to Step 9 TDD implementation in primary session per cycle-13 L2 sizing heuristic (each TASK has < 30 LOC prod + < 100 LOC tests with no novel APIs).

**Notes:**
- R1 Opus design review amendments (AC5/AC6/AC8) are folded into the plan.
- Q9 extraction-json cap corrected (design-doc inline-amended post-verdict when R2's misread was caught).
- Step 12 doc sync handles all C8/C12/C16 conditions (Codex subagent later).

## Risk log (carried over)

- **AC7 test flakiness** — 80% tolerance with N=3 + 10 trials; if CI flakes, relax to 70% or bump trials.
- **Codex hook issue** — Step 8 dispatch hung; Step 9 implementation will use primary-session TDD to avoid further hangs.
- **Session length** — Steps 1-8 already consumed significant wall-clock; Step 9 TDD-per-task discipline will be tight.
