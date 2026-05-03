# Cycle 61 — Plan gate (Step 8)

**Auditor:** mimo-v2.5-pro
**Date:** 2026-05-03
**Inputs:** plan.md (616 lines), design-decision.md (370 lines), source code direct reads + grep verification

---

## Analysis

I verified the Step 7 implementation plan against actual source code in the cycle-61 worktree by reading engine.py, hybrid.py, and compiler.py directly and cross-referencing claimed file:line targets against verified source.

### High-risk task verification findings

**Task 06 (AC10, engine.py short-circuit):**
- **Plan claim:** "line 205, inside query() method, using self._settings.kb_disable_vectors and self._keyword_search"
- **Verified source reality:** NO query() method exists; NO QueryEngine class; search_pages() is module-level function; line 205 is inside nested closure, not class method; NO self._settings or self._keyword_search attributes exist
- **Severity:** BLOCKER — plan invents class-based architecture that does not exist

**Task 07 (AC10, hybrid.py mirror):**
- **Plan claim:** "line 32, inside hybrid_search, settings parameter"
- **Verified source reality:** Line 32 is inside rrf_fusion() function (not hybrid_search); hybrid_search() starts at line 54; NO settings parameter in signature
- **Severity:** BLOCKER — wrong line number (32 vs 54) plus non-existent parameter

**Task 04 (AC22, compiler.py caller= threading):**
- **Plan claim:** "exactly three call-sites: line 178 (compile_wiki), line 214 (_prune_stale_outputs), line 263 (compile_incremental)"
- **Verified source reality:** grep found lines 575 and 809; _prune_stale_outputs() and compile_incremental() do not exist as functions
- **Severity:** BLOCKER — all three line numbers wrong; two functions hallucinated

**Task 08 (AC12, kb_rebuild_indexes MCP tool):**
- **Plan claim:** "async def kb_rebuild_indexes(caller: str = 'mcp') -> dict"
- **Design-decision reality:** AC12 tool should have NO caller param; AC22 threading is INTERNAL (tool calls rebuild_indexes(..., caller='mcp') internally)
- **Severity:** BLOCKER — conflates AC12 (public API) with AC22 (internal instrumentation)

---

## Findings

**Gap 1 (BLOCKER — Task 06, AC10):** Plan claims engine.py line 205 is inside query() method. Actual: no class; search_pages() is module-level function at line 47; line 205 is inside nested closure. Resolution: Rewrite to target search_pages() closure, use _kb_disable_vectors() function call, remove class/method language.

**Gap 2 (BLOCKER — Task 07, AC10):** Plan claims hybrid.py line 32 is top of hybrid_search() with settings parameter. Actual: line 32 is inside rrf_fusion(); hybrid_search() starts line 54; no settings parameter. Resolution: Retarget line 54, wrap vector call with _kb_disable_vectors() guard, remove settings param reference.

**Gap 3 (BLOCKER — Task 04, AC22):** Plan claims three call-sites at lines 178, 214, 263. Actual: only two sites exist at 575 and 809; _prune_stale_outputs() and compile_incremental() don't exist. Resolution: Correct targets to 575 (compile_wiki) and 809 (rebuild_indexes); remove non-existent functions.

**Gap 4 (BLOCKER — Task 08, AC12+AC22):** Plan exposes caller="mcp" in tool signature. Actual: tool should NOT expose caller; internal call threads it. Resolution: Split into (a) AC12 tool signature without caller, (b) AC22 internal call with caller="mcp".

**Gap 5 (HIGH — Task 12, AC18):** Plan references test_compile.py:152 fixture. File may have shifted. Resolution: Implementer must grep for fixture name at Step 9.

**Gap 6 (HIGH — AC11 tests):** Tests targeting AC10 will fail if BLOCKERs 1-2 not fixed. Resolution: Re-verify after fixing Tasks 06-07.

**Gap 7 (HIGH — AC13 tests):** Tests assert default caller="mcp" signature. Will fail if Task 08 corrected. Resolution: Update assertions after fixing Task 08.

**Gap 8 (HIGH — AC22 test count):** Plan implies 3 compiler.py sites; only 2 exist. Resolution: Update test count from 3 to 2.

---

## Coverage matrix audit (spot-check)

| AC | Task | Test file | Verified? | Status |
|----|------|----|-----------|--------|
| AC10 | 06, 07 | test_query.py | BLOCKER — wrong targets | REJECT |
| AC22 | 04, 08, 18 | test_utils_io.py | BLOCKER — wrong line numbers + signature | REJECT |
| AC9 | 02 | (new helper) | Matches design-decision | OK |
| AC6 | 03 | test_lint.py | Structurally OK | OK |
| AC12 | 08 | test_mcp_browse_health.py | BLOCKER — signature conflation | REJECT |

All 22 ACs present in task list. All 16 CONDITIONS mapped. But 4 high-risk tasks have factual errors.

---

## Verdict

**REJECT** — 4 BLOCKERs + 4 HIGH gaps = 8 findings preventing Step 9.

**Blocker summary:**
- Task 06 (AC10): Invents non-existent query() method and self._settings
- Task 07 (AC10): Wrong line (32 vs 54) and non-existent settings parameter
- Task 04 (AC22): All 3 line numbers wrong; 2 functions hallucinated
- Task 08 (AC12+AC22): Conflates two ACs; exposes internal caller in public tool API

**Required action:** Resolve all 4 BLOCKERs inline before Step 9:
1. Fix Task 06: Retarget to search_pages() closure at line 205, use _kb_disable_vectors() function
2. Fix Task 07: Retarget to line 54+, wrap vector_fn call, remove settings param
3. Fix Task 04: Correct targets to lines 575 and 809; remove _prune_stale_outputs() and compile_incremental()
4. Fix Task 08: Split AC12 tool (no caller param) from AC22 internal threading (caller="mcp" passed to rebuild_indexes())

After inline corrections, lightweight re-audit of blockers-only recommended before Step 9 dispatch.
