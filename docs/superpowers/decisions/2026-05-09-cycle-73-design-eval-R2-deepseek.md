# Cycle 73 — Round 2 Design Evaluation (DeepSeek V4 Pro, adversarial)

**Date:** 2026-05-09  
**Reviewer:** DeepSeek V4 Pro (cross-family adversarial R2)  
**Scope:** 6 ACs from `feat/cycle-73` against 5 evaluation categories  
**Verdict:** **APPROVE-WITH-FINDINGS** (4 findings, 0 blockers)

---

## Summary

DeepSeek identified 11 edge cases, 6 integration failure modes, and 2 security concerns. Code inspection confirms:

- **L1 (circular-import)**: PASS — `kb.config` is a leaf module.
- **L8 (cap-math marker)**: PASS — `_cap_page_content` correctly reserves marker length.
- **Marker safety**: PASS — no fence-breaking characters.
- **Same-class peers**: DEFERRED to cycle-74+ planning.

---

## Category 1: Edge cases NOT in requirements

### AC01 — build_completeness_context

**E1: Missing `paired['page_content']` key**
- Scenario: caller omits key. Failure: `KeyError` crash.
- Status: MINOR — cycle-72 AC01 likely guards same site; verify at Step 9.

**E2: Truncation marker safety**
- Marker: `"\n…[truncated for context budget]"` (no backticks, no fence chars).
- Code inspection: safe inside `wrap_wiki_context` fence.
- Verdict: PASS.

**E3: `_render_sources` budget accounting**
- Code inspection: `_render_sources` respects budget parameter per L6 contract.
- Verdict: PASS.

### AC02 — Verdict prompt-version stamp

**E1: `get_prompt_version` called with non-dict**
- Scenario: corrupted verdicts.json yields list/None. Accessor crashes on `.get()`.
- Recommendation: defensive check `isinstance(entry, dict)` before `.get()`.
- Verdict: MINOR FINDING — requirement AC02 test `test_get_prompt_version_handles_non_dict_inputs` already specified. Implementer must not skip.

### AC03 — _validate_tier_boundary

**E1: Missing required keys not rejected**
- Scenario: LLM omits key; validator only rejects extra keys. Downstream `KeyError`.
- Verdict: DEFERRED — Step 9 decides whether to reject missing keys or guard downstream.

**E2: `max_string_len=4096` may reject legitimate long values**
- Verdict: ACCEPTABLE — Q3 provides rationale.

**E3: No `max_keys` limit (DoS)**
- Scenario: LLM returns dict with 100k keys → memory exhaustion.
- Verdict: FINDING — recommend `max_keys: int = 500` default. Cycle-74+ BACKLOG candidate.

### AC05 — Snapshots

**E1: Non-deterministic ordering**
- Scenario: `_render_sources` iterates unordered dict.
- Verdict: MINOR — Step 9 must sort sources before snapshot.

---

## Category 2: Integration failure modes

**AC03+AC04**: `ValidationError` must be caught before generic `Exception`.
- Verdict: PASS (design is sound; Step 14 grep will verify).

**AC01 + marker**: Marker is safe inside wrap fence.
- Verdict: PASS.

**AC02 + retry loop**: With E1 fix, no crash on non-dict.
- Verdict: PASS.

---

## Category 3: Security / perf

**AC03-S1: No max-keys limit (DoS)**
- Worst-case: 100k keys → memory spike.
- Verdict: FINDING — file cycle-74+ BACKLOG.

**AC02-S1: JSON write bottleneck**
- Verdict: ACCEPTABLE — not in cycle-73 scope.

---

## Category 4: Same-class peer scan

**AC01**: cap+wrap pattern should be checked at other prompt-builder sites (cycle-74+).

**AC03**: tier-boundary validator should be applied to all `_call_llm_json` sites (cycle-74+).

Proposed BACKLOG entries post-cycle-73.

---

## Category 5: Cycle-72 lessons

**L1 (circular-import)**: `kb.config` is a leaf module. PASS.

**L8 (cap-math marker)**: `_cap_page_content` reserves marker length within `max_chars`. PASS.

**M-1 (Codex fix)**: `max_chars - len(marker)` is used for slicing. PASS.

---

## Findings summary

| Finding | Category | AC | Recommendation |
|---------|----------|----|----|
| F-1: `get_prompt_version` defensive check | AC02 | Test already specified; don't skip |
| F-2: No max-keys limit (DoS) | AC03 | Cycle-74+ BACKLOG: "add max_keys default 500" |
| F-3: Missing-key validation scope | AC03 | Step 9 design decision + Step 10 test |
| F-4: Peer scope (AC01, AC03 expansion) | L1 | Cycle-74+ planning: grep all sites |

---

## Blockers

**NONE.** All findings have mitigation strategies or are deferred to cycle-74+.

---

## Verdict

**APPROVE-WITH-FINDINGS**

- 4 findings (0 blockers).
- Cycle-72 lessons L1 + L8 correctly applied.
- Proceed to Step 5 (implementation).
- File BACKLOG entries post-cycle-73 for scope expansions.
