# Cycle 70 PR #98 --- R1 Sonnet Review

**Date:** 2026-05-08
**Reviewer:** Sonnet 4.6
**Verdict:** APPROVE-WITH-CONDITIONS

## Summary

PR #98 ships 16 ACs across 6 buckets: BACKLOG hygiene, 3 snapshot subjects deferred from cycle-64, 1 cycle-69 carry-over date-coverage audit, 1 C41-L1 behavioural spy upgrade, 2 NEW ACs for the wrap_wiki_context prompt-injection boundary fence, and doc artifacts. CI is CLEAN (3302 passed + 24 skipped in 175s, ruff clean, pip-audit 0 new alerts, mergeStateStatus=CLEAN).

The core implementation is correct and mirrors the cycle-7 wrap_purpose precedent. _FENCE_OVERHEAD=183 verified (1+149+1+15+1+16). T3 escape (count==1) is stronger than PA-3 spec. T4 short-circuit before fence-tag computation is correct. Snapshot subjects are deterministic with paired negative-controls. Two medium-severity findings are identified.

## HIGH/MAJOR (binding)

None.

## MEDIUM (likely binding)

### M1 - T5 budget-awareness test absent (PA-3 non-compliance)

Plan-gate PA-3 (binding amendment) required for TASK 8: "T5 (budget-awareness): assert len(final_prompt) <= QUERY_CONTEXT_MAX_CHARS". The shipped test_fence_overhead_constant_exposed only verifies _FENCE_OVERHEAD is importable, int, and in (50,500). It does NOT exercise the budget arithmetic at engine.py:1054.

The engine integration test stubs search_raw_sources=[], so the raw_fallback branch (lines 1045-1064) is never entered and line 1054 is never executed. Removing _FENCE_OVERHEAD from the budget subtraction at engine.py:1054 would not be caught by any current test.

Risk: MEDIUM-LOW. The fence-overhead reservation is a 184-char overshoot protection, not a security boundary. But it is an explicit PA-3 binding requirement that was not delivered.

Suggested fix (non-blocking): Add a test that exercises _query_wiki_body with a near-full ctx context and non-empty raw_results, asserting the budget clamping keeps combined context within QUERY_CONTEXT_MAX_CHARS.

### M2 - Negative budget edge case at engine.py:1054 (pre-existing worsened)

When len(ctx["context"]) >= QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD (i.e. context near-full at 80000 chars from all-summary pages with raw_fallback_needed=True), budget = QUERY_CONTEXT_MAX_CHARS - 80000 - 183 = -183. At line 1057 any section satisfies len(section) > budget (negative). The first-section branch appends section[:-183] (empty-ish string). raw_sections = [""] is truthy so raw_context = "\n". Combined context = 80001 chars; wrap adds 183 = 80184 chars in prompt, overshooting QUERY_CONTEXT_MAX_CHARS by 184.

Pre-cycle-70 code had budget=0 at the same fill level (appending section[:0]=""), so the pre-existing bug was empty raw_sections. The new subtraction worsens overshoot by 183 chars.

Risk: LOW. Requires context to exactly fill QUERY_CONTEXT_MAX_CHARS with summary-only pages triggering raw fallback simultaneously. In practice context mixes page types. The 184-char overshoot is small relative to model context windows.

Fix pattern: budget = max(0, QUERY_CONTEXT_MAX_CHARS - len(ctx["context"]) - _FENCE_OVERHEAD). One-liner.

## LOW / NIT (suggested)

### N1 - if wrapped: guard in mcp/core.py is vacuous

Source: src/kb/mcp/core.py lines 439-441. results is guaranteed non-empty by early return at lines 396-400. Each page_sections entry always contains non-empty "--- Page: ..." header text. wrap_wiki_context always returns non-empty string. The "if wrapped:" guard is dead code. Harmless but misleading.

### N2 - AC09 date-string lock-in is vacuous on its commit date

Source: tests/test_cycle70_snapshots.py lines 278-279 (acknowledged in comment). The test asserts "2026-05-08" in rendered. Since today is 2026-05-08, removing the monkeypatch also yields "2026-05-08" via date.today(), so the assertion passes vacuously today. Acknowledged in comment at line 278. Cycle-69 AC14 snapshot test provides today-time mutation guard; cycle-70 is forward-looking only. Non-blocking.

### N3 - T5 range assertion lower bound may be too tight

Source: tests/test_cycle70_prompt_safety.py line 229. Range is (50, 500). Current value is 183. Shortening the assertion sentence below 36 chars would push overhead below 50 and trip the lower bound. Consider assert _FENCE_OVERHEAD == 1 + len(_WIKI_CONTEXT_ASSERTION) + 1 + len("<wiki_context>\n") + 1 + len("</wiki_context>\n") as a self-synchronizing alternative. Deferred.

## AC-by-AC analysis

| AC | Verdict | Notes |
|----|---------|-------|
| AC01 | APPROVE | httpx>=0.28,<0.29 at pyproject.toml:30 confirmed; BACKLOG entry deleted; lock-in substring present. |
| AC02 | APPROVE | README.md:137-148 KB_PROJECT_ROOT bootstrap section confirmed; BACKLOG entry deleted. |
| AC03 | APPROVE | KB_STRICT_PUBLISH at compile/compiler.py:619,624 + query/hybrid.py:21 confirmed; BACKLOG entry deleted. |
| AC04 | APPROVE | Zero inspect.getsource() function-call hits in 4 versioned files (only comment/docstring refs); BACKLOG entry deleted. |
| AC05 | APPROVE | 6 substrings per C1 added to DELETED_ENTRIES. All 6 verified absent from BACKLOG.md. |
| AC06 | APPROVE | Fixture per A1 (key_claims, NOT contradictions). 2 authors plural. Negative-control varies entity name. Determinism per C2. |
| AC07 | APPROVE | Shared _build_fixture_wiki helper. Explicit dates per C3. incremental=False. Negative-control body change. |
| AC08 | APPROVE | Re-parse + sort_keys per A4. Production unchanged. Negative-control removes one wikilink. |
| AC09 | APPROVE-WITH-NIT | N2 above. Forward-looking lock-in works post-2026-05-08. Cycle-69 snapshot provides today-time primary guard. |
| AC10 | APPROVE | Mock(wraps=compiler._canonical_rel_path) per C5. Two parametrized branches drift_detect + full_mode. inspect import cleanly removed. Mutation budget: removing _canonical_rel_path from either site fails its branch. |
| AC11 | APPROVE-WITH-CONDITIONS | Helper correct; _FENCE_OVERHEAD=183 verified; T3 escape via regex; T4 short-circuit before fence computation; system prompt assertion at engine.py:1112. Budget reservation at line 1054 correct in intent. See M1 (test gap) and M2 (negative-budget edge case). |
| AC12 | APPROVE-WITH-CONDITIONS | 6 tests cover T1/T3/T4/T5-constant/both-spy-sites. See M1: PA-3 T5 budget-awareness assertion (len(prompt) <= QUERY_CONTEXT_MAX_CHARS at high ctx fill) absent. Spy patching pattern (hasattr conditional for module-scope imports) is correct. |
| AC13 | APPROVE | 8 decision artifacts confirmed. |
| AC14 | APPROVE | CHANGELOG.md + CHANGELOG-history.md both updated with cycle-70 per-AC detail. |
| AC15 | APPROVE | CLAUDE.md test count 3288 to 3302; wrap_wiki_context bullet with both wiring sites and _FENCE_OVERHEAD note. |
| AC16 | APPROVE | 6 BACKLOG deletions confirmed. 4 NEW Phase 4.5 LOW entries for out-of-scope sites (cycle-71+). |

## Verdict (final)

APPROVE-WITH-CONDITIONS. M1 (PA-3 T5 test gap) and M2 (negative-budget edge case) are MEDIUM severity but non-blocking given CI green and production risk LOW for M2 (requires extreme context fill + raw fallback simultaneously) and no security regression for M1 (budget reservation logic is correct; only the test for it is weaker than specified). Both are candidates for cycle-71 BACKLOG entries. R2 should independently probe M2; if confirmed as production risk, add max(0, budget) one-liner before merge.
