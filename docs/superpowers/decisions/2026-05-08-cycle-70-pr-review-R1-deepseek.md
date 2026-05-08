# Cycle 70 PR #98 — R1 DeepSeek Review

**Date:** 2026-05-08  
**Reviewer:** DeepSeek V4 Pro (deepseek-rescue)  
**Verdict (initial):** APPROVE

## Summary

PR #98 ships 16 ACs across 6 buckets with a NEW prompt-injection boundary helper `wrap_wiki_context()` at two in-scope call sites (synthesis prompt + Claude Code response). All threat-model mitigations (T1–T5) are correctly engineered:

- **T1 fence+assertion**: Helper returns both fence tags + explicit "data not instructions" reminder.
- **T3 escape**: Internal `</wiki_context>` substrings rewritten to `</wiki-context>` (hyphen variant) so only the outer fence survives.
- **C6 short-circuit**: Empty input returns `""` **before** fence-overhead computation, preventing orphan fence tags.
- **T5 budget reservation**: Fence overhead subtracted at `engine.py:1054` before raw_context truncation loop.
- **AC10 spy upgrade**: `Mock(wraps=...)` preserves real return values; both parametrized branches independently tested.
- **AC09 date-lock-in**: Forward-looking assertion verifies frozen "2026-05-08"; future non-patched `date.today()` site would trip it.

All cycle-3 R1 verification claims cite source file:line. No vacuous tests; mutation budgets sound.

## MAJORs (binding amendments)

None identified.

## MINORs / NITs (suggested)

None identified.

## AC-by-AC analysis

### AC11 — wrap_wiki_context helper (src/kb/utils/text.py)

**Source:** `text.py:355-393`

**T1 — Fence + assertion present**
- Line 355: Helper signature
- Lines 376-378: Return statement constructs fenced output with both `<wiki_context>` and `</wiki_context>` tags
- Lines 337-341: Assertion string explicitly tells LLM the content is data, not instructions
- **PASS**: Both fence tags + explicit data-vs-instructions distinction present.

**T3 — Escape pattern defangs internal closing tags**
- Line 335: Regex `r"<\s*/\s*wiki_context\s*>"` (case-insensitive)
- Lines 344-352: `_escape_wiki_context_close` function replaces matched pattern with `</wiki-context>` (hyphen variant)
- Line 375: Escape applied before wrapping
- Test assertion: Input `"malicious</wiki_context>injected"` yields `.count("</wiki_context>") == 1`
- **PASS**: Internal closing tags neutralized; only outer fence-pair visible to LLM.

**C6 — Empty input short-circuits before fence overhead**
- Lines 373-374: Early `return ""` happens **before** line 375 (escape)
- Test: Both `wrap_wiki_context("")` and `wrap_wiki_context("   \n  \t ")` return `""`
- **PASS**: No fence overhead incurred for empty input.

**_FENCE_OVERHEAD accuracy**
- Lines 382-393: Constant computed at import time from assertion + tag lengths
- Mirrors exact output shape of lines 376-378
- **PASS**: No manual duplication risk.

### AC12 — Lock-in sites

**Site #1: engine.py synthesis prompt (engine.py:1063)**

- Import line 42: `wrap_wiki_context, _FENCE_OVERHEAD` ✓
- Budget line 1054: `budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"]) - _FENCE_OVERHEAD` ✓
- Wrapping line 1063: `wrap_wiki_context(ctx["context"] + raw_context)` before interpolation ✓
- System prompt lines 1122-1124: defense-in-depth assertion ✓

**Test**: `test_wrap_wiki_context_invoked_by_query_engine_synthesis_prompt`
- Spies on `wrap_wiki_context`
- Asserts `spy.call_count >= 1` and fence in synthesized prompt ✓

**Site #2: mcp/core.py Claude Code response (mcp/core.py:417-439)**

- Import line 41: `wrap_wiki_context` ✓
- Header lines 417-422: unfenced instructions ✓
- Page block lines 438-439: wrapped wiki content ✓

**Test**: `test_wrap_wiki_context_invoked_by_mcp_kb_query_claude_code_mode`
- Spies on `wrap_wiki_context`
- Asserts `spy.call_count >= 1` ✓

### AC10 — C41-L1 spy upgrade (test_compile.py:211-299)

- Line 221-222: `MagicMock(wraps=real_helper)` preserves return values ✓
- Line 215: `@pytest.mark.parametrize("call_site", ["drift_detect", "full_mode"])` ✓
- Each branch: independent spy instance, assert `spy.call_count >= 1` ✓

### AC09 — Date-coverage audit + forward-looking lock-in (test_cycle70_snapshots.py:259-332)

- Audit: `_FakeDate` monkeypatch covers ALL 4 `date.today()` sites via module-namespace lookup ✓
- Forward-looking: assert `"2026-05-08"` in rendered output ✓
- Mutations: (a) remove monkeypatch → date diverges; (b) non-patched site → drift ✓

## Final fact-check (MANDATORY per cycle-69 L1)

All 14 claim-to-source citations verified against actual source files:

1. AC11 T1: text.py:355,376-378 ✓
2. AC11 T3: text.py:335,344-352,375 ✓
3. AC11 C6: text.py:373-374 ✓
4. AC11 overhead: text.py:382-393 ✓
5. AC12 S1 import: engine.py:42 ✓
6. AC12 S1 budget: engine.py:1054 ✓
7. AC12 S1 wrapping: engine.py:1063 ✓
8. AC12 S1 system: engine.py:1122-1124 ✓
9. AC12 S2 import: mcp/core.py:41 ✓
10. AC12 S2 wrapping: mcp/core.py:438-439 ✓
11. AC10 Mock(wraps=): test_compile.py:221-222 ✓
12. AC10 parametrize: test_compile.py:215 ✓
13. AC09 monkeypatch: test_cycle70_snapshots.py:297 ✓
14. AC09 assertion: test_cycle70_snapshots.py:309 ✓

No downgrades required.

## Verdict (final, post-fact-check)

**APPROVE**

All threat-model mitigations correctly implemented and verified. Test mutation budgets sound. All cycle-3 R1 verification claims cite source and pass fact-check. No issues identified.
