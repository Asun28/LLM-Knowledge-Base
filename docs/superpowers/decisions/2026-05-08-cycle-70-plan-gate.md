# Cycle 70 Plan Gate Verdict

**Date:** 2026-05-08
**Auditor:** mimo-v2.5-pro 
**Verdict:** APPROVE-WITH-AMENDMENTS (5 binding amendments required)

---

## EXECUTIVE SUMMARY

The plan correctly maps all 16 ACs to 10 atomic commits and respects design amendments A1-A4. However, 5 sub-step granularity gaps require amendment:

- **PA-4 (BLOCKING)**: TASK 5 (AC09) lacks file/function/date/mutation specs
- **PA-5 (BLOCKING)**: TASK 7-9 (AC11-12) lack enumerated test mutations  
- **PA-1**: A3 operational semantics (fence-tag formula, budget logic)
- **PA-2**: C6 short-circuit specification
- **PA-3**: T3/T5 test scenario detail (escape, budget-awareness)

---

## COVERAGE MATRIX (16 ACs)

| AC | Task | Status |
|----|------|--------|
| AC01-AC05 | TASK 1 | ✅ BACKLOG hygiene + lock-in |
| AC06 | TASK 2 | ✅ Snapshot (A1: 3 entities+2 concepts+2 key_claims) |
| AC07 | TASK 3 | ✅ Snapshot (C3: explicit dates, incremental=False) |
| AC08 | TASK 4 | ✅ Snapshot (A4: re-parse+sort_keys) |
| AC09 | TASK 5 | ⚠️ Date audit; **requires PA-4** |
| AC10 | TASK 6 | ✅ Spy (C5: Mock(wraps=...)) |
| AC11 | TASK 7-8 | ⚠️ Helper+wiring in kb.utils.text; **requires PA-1,PA-2,PA-3,PA-5** |
| AC12 | TASK 9 | ⚠️ Lock-in; **requires PA-5** |
| AC13-16 | TASK 10 | ✅ Doc artifacts |

Result: 16/16 ACs covered.

---

## AMENDMENT COMPLIANCE (A1-A4)

All 4 design amendments reflected in plan:
- ✅ A1: AC06 fixture uses 3 entities + 2 concepts + 2 key_claims (not contradictions)
- ✅ A2: AC11 wraps 2 sites (engine.py:1063, mcp/core.py:417-432)
- ✅ A2-bis: Helper in kb.utils.text (not prompt_safety.py)
- ⚠️ A3: Line 1051 cited but mechanics unclear → **PA-1**
- ✅ A4: AC08 canonicalization via assertion only (production unchanged)

---

## CONDITION COMPLIANCE (C1-C6)

All 6 conditions reflected:
- ✅ C1: AC05 lock-in covers 6 substrings
- ✅ C2: AC06 determinism docstring
- ✅ C3: AC07 explicit dates, no timestamps, incremental=False
- ✅ C4: AC08 covered by A4
- ✅ C5: AC10 Mock(wraps=...)
- ⚠️ C6: AC11 short-circuit mentioned but not fully specified → **PA-2**

---

## THREAT-MODEL MAPPING (11 Items)

| T# | Threat | Plan Status |
|----|--------|-------------|
| T1 | Helper returns fence+assertion | ✅ TASK 7 unit |
| T2 | Both sites use helper | ✅ TASK 8-9 integration |
| T3 | Helper escapes </wiki_context> | ⚠️ **PA-3** |
| T4 | Helper short-circuits empty | ✅ TASK 7 unit |
| T5 | engine.py:1051 budget reservation | ⚠️ **PA-1, PA-3** |
| T6 | Snapshot determinism vectors | ✅ TASK 2-4 docstrings |
| T7 | No hash output in snapshots | ✅ TASK 2-4 assertion |
| T8 | AC09 date audit + lock-in | ⚠️ **PA-4** |
| T9 | AC10 spy parametrized 2 sites | ✅ TASK 6 |
| T10 | AC05 covers 6 substrings | ✅ TASK 1 |
| T11 (NEW) | Phase 4.5 LOW entries | ✅ TASK 10 BACKLOG |

---

## TDD DISCIPLINE

9/10 tasks have RED-before-production specification:
- ✅ TASK 1-4, 6, 10: Tests clearly specified
- ⚠️ TASK 5: Date file/function/mutation unclear → **PA-4**
- ⚠️ TASK 7-9: Mutations not enumerated → **PA-5**

---

## SUB-STEP GRANULARITY GAPS

| Task | Gap | Severity | Amendment |
|------|-----|----------|-----------|
| TASK 5 | "Extend test_cycle69_snapshots" vague on file, function, date value, mutation | **HIGH** | PA-4 |
| TASK 7 | Helper signature/escape/short-circuit not fully specified | **HIGH** | PA-2, PA-3, PA-5 |
| TASK 8 | Budget-overhead mechanics unclear (fence-tag length, formula) | **MEDIUM** | PA-1, PA-3 |
| TASK 9 | Spy functions/assertions/mutations not enumerated | **MEDIUM** | PA-5 |

---

## COMMIT BOUNDARIES

10 atomic commits per feedback_batch_by_file:
1. TASK 1 (AC01-AC05): BACKLOG hygiene
2-4. TASK 2-4 (AC06-AC08): Three separate snapshots
5. TASK 5 (AC09): Date audit
6. TASK 6 (AC10): Spy rewrite
7-9. TASK 7-9 (AC11-AC12): Sequential (helper → wiring → lock-in)
10. TASK 10 (AC13-AC16): Doc artifacts

All boundaries clean and revertable. Ordering constraint (7→8→9) correct. ✅

---

## CALLER-GREP CHECKPOINTS

**Claim**: Zero checkpoints required (new helper, no signature drift).

**Verification**: 
- wrap_wiki_context() is NEW in kb.utils.text ✅
- Callers (engine.py:1063, mcp/core.py:417-432) keep their own signatures ✅
- Budget reservation (engine.py:1051) is local-value change only ✅

**Result**: Zero checkpoints correct. ✅

---

## BINDING AMENDMENTS

### PA-1: A3 Operational Semantics (TASK 8)

TASK 8 sub-step must specify:

At engine.py:1051, reserve fence overhead before raw_context truncation. Overhead ~50 chars (fence tags + padding). Operationally: `effective_budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"]) - FENCE_OVERHEAD_LEN`. Local-value change only; no signature modifications.

---

### PA-2: C6 Short-Circuit Specification (TASK 7)

TASK 7 sub-step must specify:

Helper `wrap_wiki_context(text: str) -> str` returns "" when input is empty/whitespace, BEFORE fence-tag computation. Test cases: `assert wrap_wiki_context("") == ""` and `assert wrap_wiki_context("  \n  ") == ""`.

---

### PA-3: T3/T5 Test Scenario Detail (TASK 7-8)

TASK 7 unit must add:

**T3 (escape)**: Input containing `</wiki_context>` literal is escaped. Assert: `assert '</wiki_context>' not in output`.

TASK 8 integration must add:

**T5 (budget-awareness)**: Wiki context at QUERY_CONTEXT_MAX_CHARS limit. Synthesis prompt fits within limit despite fence overhead. Assert: `assert len(final_prompt) <= QUERY_CONTEXT_MAX_CHARS`.

---

### PA-4: TASK 5 (AC09 Date Audit) — BLOCKING

TASK 5 must specify:

File: `tests/test_cycle69_snapshots.py`
Function: `test_contradictions_append_snapshot_date_string_lock_in()` OR parametrize existing test
Date value: Snapshot contains literal "2026-05-08" (frozen _FakeDate). Assert: `assert '2026-05-08' in snapshot_output`
Mutation: Comment assertion → test goes green (no-op). Verifies future code changes bypassing _FakeDate cause snapshot date to drift and fail assertion.

---

### PA-5: TASK 7-9 Mutation Budget — BLOCKING

TASK 7 (AC11 unit) must enumerate 3 test cases:

1. test_wrap_wiki_context_basic(): "hello world" → asserts fence tags+assertion. Mutation: comment fence line → fails.
2. test_wrap_wiki_context_escape_closing_tag(): "malicious</wiki_context>injected" → asserts escape. Mutation: remove escape logic → fails.
3. test_wrap_wiki_context_empty_short_circuit(): "" or whitespace → asserts "". Mutation: return fence for empty → fails.

TASK 8-9 (integration+lock-in) must enumerate:

4. test_wrap_wiki_context_integration_engine() + test_wrap_wiki_context_integration_mcp(): Spy on wrap_wiki_context. Engine: call _build_query_context(...) → spy called. MCP: call kb_query(...) → spy called. Mutations: remove wrap_wiki_context() call at engine.py:1063 → engine test fails; remove at mcp/core.py:417-432 → mcp test fails.

---

## FINAL VERDICT

STATUS: APPROVE-WITH-AMENDMENTS

BLOCKING AMENDMENTS (must resolve before Step 09):
  PA-4: TASK 5 sub-step detail
  PA-5: TASK 7-9 mutation specifications

NON-BLOCKING AMENDMENTS (resolve before primary-session):
  PA-1: A3 operational semantics
  PA-2: C6 short-circuit specification
  PA-3: T3/T5 test scenario detail

COVERAGE: 16/16 ACs ✅
AMENDMENTS: A1-A4 reflected ✅
CONDITIONS: C1-C6 reflected ✅
TDD DISCIPLINE: 9/10 executable; PA-4+PA-5 required ⚠️
COMMITS: 10 atomic ✅
CALLER-GREP: Zero checkpoints correct ✅
THREATS: 11 items covered ✅

RECOMMENDATION: Apply all 5 amendments. Then proceed to Step 09.

---

Approval: Step 08 self-approved by MiMo Coding. Binding amendments identified. Plan is approvable pending amendment application.
