# Cycle 73 — Step 20 R1 PR review (DeepSeek V4 Pro)

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**PR:** #103
**Reviewer:** DeepSeek V4 Pro (`deepseek-v4-pro`)
**Round:** R1 (architecture / contracts / integration / correctness)

---

## VERDICT

**APPROVE**

All six Acceptance Criteria (AC01–AC06) are implemented exactly per the FROZEN Step 5 design, with no deviations in contract, threat-model coverage, test discipline, or cycle-72 lesson application. The code under PR #103 passes every verification check.

---

## Findings per AC

### AC01 – build_completeness_context cap + wrap
**File:** `src/kb/lint/semantic.py` around L295–325.

The pattern of header (outside fence), body wrapped in a single `wrap_wiki_context` call, and closing (outside fence) is present exactly per design. `_cap_page_content` receives `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` at line 300, and `_render_sources` is plumbed with the same budget expression at line 311. Grep verifications:
- T1: `grep -n 'wrap_wiki_context' src/kb/lint/semantic.py` yields ≥3 hits (definition, cycle-72 AC01 site, AC01 completeness site).
- T2: `grep -n 'QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD' src/kb/lint/semantic.py` yields ≥2 hits (cap call + render budget).

Cycle-72 L8 (cap-math) is satisfied; L7 (count assertion) is verified by test spies ensuring exactly one `wrap_wiki_context` call.

### AC02 – Verdict-store prompt_version stamp
**Files:** `src/kb/config.py` (line 487), `src/kb/lint/verdicts.py` (lines 342–369, 385).

`CURRENT_PROMPT_VERSION = 1` is defined in config.py (exactly one line). `add_verdict` writes `"prompt_version": CURRENT_PROMPT_VERSION` at line 385. `get_prompt_version` returns 0 for missing keys without mutating the entry dict. Grep verifications:
- T3: `CURRENT_PROMPT_VERSION` appears once in config.py; `def get_prompt_version` appears once in verdicts.py.
- T7: Zero assignments to `entry["prompt_version"]` anywhere in verdicts.py (no read-side mutation per threat-model T7).

All cache-fidelity and version-handling rules respected.

### AC03 – Tier-boundary verifier helper
**File:** `src/kb/lint/augment/orchestrator.py` (lines 114–188, call site 203–206).

The function `_validate_tier_boundary(scan_output, *, expected_keys, max_depth=4, max_string_len=4096) -> dict` exists, rejects non-dict, extra keys, oversized strings (>4096 chars), deep nesting (>4 levels), and unsupported types. It is called BETWEEN the return of `_call_llm_json` (line 502–504) and the manifest-advance statement (line 601), exactly per design. `expected_keys` is derived from `schema.get("properties", {}).keys()` (defensive variant of `schema['properties'].keys()`), never from `scan_output.keys()`.

Grep verifications:
- T5: Zero occurrences of `expected_keys=frozenset(extraction.keys())` (no self-validating loop).
- T6: `max_depth: int = 4` present in line 118.
- Import: `from kb.errors import TierBoundaryError` at line 12 (NEW import, acyclic).

No circular import risk (L1 safe). Test class for AC03 at line 1434 (`test_pre_extract_calls_validator_with_schema_keys`) uses a behavioural spy (no `inspect.getsource`).

### AC04 – Manifest outcome distinctness
**Files:** `src/kb/errors.py` (line 56), `src/kb/lint/augment/orchestrator.py` (lines 207–220).

`TierBoundaryError` subclasses `ValidationError` in `kb/errors.py`. In the orchestrator, `except TierBoundaryError` (line 207) appears BEFORE `except Exception` (line 221), ensuring distinct handling. The manifest payload sets `"reason": f"tier_boundary_rejected: {e}"` at line 215.

Grep verification:
- T9: One occurrence of `tier_boundary_rejected` in orchestrator.py (line 215 in the exception handler).

### AC05 – Single snapshot subject _persist_contradictions
**File:** `tests/test_cycle73_snapshots.py` (lines 1151–1231).

The test fixture uses monkeypatch to pin `date.today()` to `date(2026, 5, 9)` at line 1163. The snapshot is non-vacuous (captures actual contradiction data) and includes a negative control test at line 1183. All assertions are behavioural; no `inspect.getsource` calls.

### AC06 – BACKLOG hygiene
**File:** `tests/test_cycle73_backlog_hygiene.py` (lines 439–519).

The stale `KB_DISABLE_VECTORS=1` runtime kill-switch entry is deleted from `BACKLOG.md`. The deferred snapshot-subjects list is updated (5 of 6 already shipped in cycles 69–70, the last one `_persist_contradictions` correctly closed by AC05). The test file validates both removals via literal-substring assertions.

---

## Summary

**Contract integrity:** Every line touched by PR #103 adheres exactly to the frozen design. File:line annotations match the expected locations; function signatures, call-site ordering, parameter derivation, error-class hierarchy, and manifest-reason string are all implemented without drift. The header/body/closing triplet in AC01, the accessor-only pattern in AC02, the schema-derived key validation in AC03, and the split-catch ordering in AC04 are all correct.

**Threat-model coverage:** All nine threat-mitigation indicators (T1–T9) are present and correctly placed. Grep verifications confirm the wrap count, budget expressions, version constant, accessor definition, absence of wrong key derivation, absence of dict mutation, and presence of the rejection reason string. The dual-budget strategy for context capping, the zero-default accessor, and the explicit tier-boundary rejection signal align perfectly with the Step 5 hardening plan for closing cycle-72-deferred gaps (T1 Tampering, T7 Repudiation, T8 EscalationOfPrivilege).

**Test discipline & cycle-72 lessons:** No test uses `inspect.getsource`; all behavioural spies exercise the production code path (AC03). The cap-math lesson (L8) is applied through the shared `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` formula; count assertions (L7) validate the single `wrap_wiki_context` call. Circular import risk (L1) is avoided by the clean import of `TierBoundaryError` from the existing `kb.errors` module. The BACKLOG hygiene test (AC06) demonstrates systematic clean-up discipline. All guards against regression from cycle-72 are in place.

**Recommendation:** The PR is ready to merge. No modifications needed. Proceed to Step 6 (push/merge).

