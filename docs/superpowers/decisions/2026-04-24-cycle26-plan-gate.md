The plan explicitly maps AC1-AC8 plus AC2b and all 13 design CONDITIONS to TASKs, grep checks, or named tests, and it does not contradict the Step 5 design dependencies. But the gate still fails: T1 from the threat model has no explicit TASK-level pin in the plan, and TASKS 2-4 each ship code while deferring verification to TASK 5 instead of stating their own failing assertions. Per the gate contract, missing threat coverage is `UNCOVERED`, so the verdict is `REJECT`. `PLAN-AMENDS-DESIGN-DISMISSED:` task ordering remains dependency-safe; no design dependency is violated.

| AC | TASK | Verification mechanism |
|---|---|---|
| AC1 | TASK 2 | TASK 5 Tests 1-3,7 |
| AC2 | TASK 4 | TASK 1 existing boot-lean test; TASK 5 Test 6 |
| AC2b | TASK 1 | Existing cycle-23 boot-lean test |
| AC3 | TASK 3 | TASK 5 Test 4 |
| AC4 | TASK 2 | TASK 5 Test 5 |
| AC5 | TASK 5 | Seven named tests in plan |
| AC6 | TASK 6 | `rg "ctx\.Process|mp\.Process|get_context"` + integration marker grep |
| AC7 | TASK 6 | `pip-audit --format=json` baseline compare |
| AC8 | TASK 6 | `BACKLOG.md:109` narrow + Q16 follow-up per CONDITION 12 |

| CONDITION | TASK | Grep/test assertion |
|---|---|---|
| 1 | TASK 1 | Existing boot-lean test enforces `kb.query.embeddings` absent after bare `import kb.mcp` |
| 2 | TASK 5 | Seven named tests present |
| 3 | TASK 3 | TASK 5 Test 4; post-success ordering text in TASK 3 |
| 4 | TASK 5 | `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` in log-observing tests |
| 5 | TASK 2 | Counter docstring/comment cites cycle-25 Q8 asymmetry |
| 6 | TASK 6 | `pip-audit` compare; no BACKLOG edit if unchanged |
| 7 | TASK 6 | Broadened grep pattern plus `@pytest.mark.integration`/`import multiprocessing as mp` |
| 8 | TASK 4 | `rg "^from kb\.query\.embeddings|^import kb\.query\.embeddings" ...` -> 0 matches |
| 9 | TASK 4 | `rg "maybe_warm_load_vector_model" src/` -> exactly 2 matches |
| 10 | TASK 2 | Wrapper catches `Exception` and logs `logger.exception` |
| 11 | TASK 4 | `try/except RuntimeError` around warm-load call |
| 12 | TASK 6 | AC8 narrow plus new Q16 backlog sub-item |
| 13 | TASK 8 | CHANGELOG/CHANGELOG-history/CLAUDE entries reflect cycle-26 counts/scope |

| Threat | Pinned by |
|---|---|
| T1 | `UNCOVERED` |
| T2 | TASK 2 text + TASK 5 Tests 2-3 |
| T3 | TASK 5 Test 2/5 `.join(timeout=5)` before cleanup |
| T4 | TASK 2 CONDITION 5 docstring pin + TASK 3 locked-counter text + TASK 5 Test 5 |
| T5 | TASK 1 module-scope import guard + TASK 4 CONDITION 9 grep |
| T6 | TASK 2 wrapper, TASK 4 startup swallow, TASK 5 Test 7 |

**Gaps**
- `T1` is not assigned to any TASK and no plan test/grep pins the lazy-format path-logging check from the threat model. This is `UNCOVERED` and requires plan amendment.
- Checklist item 4 fails: TASKS 2, 3, and 4 ship code but only say `Tests: deferred to TASK 5`; they do not each specify their own failing test assertions.
- Checklist item 5 passes: no design dependency is contradicted; the mismatch is coverage granularity, not design drift.

**Verdict:** `REJECT`
