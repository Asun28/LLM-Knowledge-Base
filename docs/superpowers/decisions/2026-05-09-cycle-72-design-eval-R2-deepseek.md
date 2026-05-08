# Cycle 72 Design Evaluation — R2 Cross-Family (DeepSeek V4 Pro)

**Date:** 2026-05-09  
**Cycle:** 72  
**Reviewer:** DeepSeek V4 Pro (adversarial R2)  
**Primary Reviewer (R1):** Opus 4.7 (parallel)

---

## Executive Summary

R2 adversarial scan identifies **5 critical gaps** that R1 (Opus) will likely miss:
1. Asymmetric capping of `build_completeness_context` (same-class peer to fidelity)
2. Non-atomic test design for review context + checklist pipeline
3. Fence-tag inconsistency across three sentinel schemes
4. Vacuous lock-in risk from attribute-form imports
5. Tautological overhead constant (definition-based test)

**Verdict:** BLOCK — these are exploitable vulnerabilities or test-validity failures requiring fix before approval.

---

## Findings

### F-1: [HIGH] Asymmetric capping — `build_completeness_context` is same-class peer

**Where:** `src/kb/lint/semantic.py:367-397` (line 386: `paired["page_content"]` read)

**Risk:** `build_completeness_context()` reads `paired["page_content"]` identically to `build_fidelity_context()` at line 82, and both call `_render_sources()` on the same list. Cycle 72 AC01 caps `build_fidelity_context` but leaves `build_completeness_context` unhardened. This creates asymmetric LLM context exposure — any content-injection bypass discovered in fidelity checks will likely work in completeness checks unless BOTH are capped.

**Recommendation:** Either add `build_completeness_context` as AC02 (capping peer), or document why the identical threat surface does not require identical protection.

---

### F-2: [HIGH] Non-atomic pipeline test for review context + checklist

**Where:** `src/kb/review/context.py:146-229` (line 227 calls `build_review_checklist()`)  
**Test design:** AC07 (pending — not yet sampled)

**Risk:** The review checklist is constructed from the review context. If AC07 tests the functions separately (e.g., unit tests calling each in isolation), the test may pass even if `build_review_context` is capped but the downstream checklist-building path reads the same uncapped content via a different accessor, or if the full dataflow is never exercised with oversized content. The test would then be signature-only, not regression-proof.

**Recommendation:** AC07 must construct the FULL pipeline with realistic oversized `paired["page_content"]` flowing from `pair_page_with_sources()` through `build_review_context()` to the checklist inclusion, asserting that no uncapped content leaks at any stage.

---

### F-3: [MEDIUM] Fence-tag semantic inconsistency

**Where:** 
- `src/kb/review/context.py:195-209` — `<wiki_page_body>` and `<raw_source_N>` tags
- `src/kb/lint/augment/orchestrator.py:368` — `<untrusted_source>` tag
- `src/kb/utils/text.py:355-378` — `<wiki_context>` tag (cycle 72 standard)

**Risk:** Three different XML tags with unclear semantic boundaries create ambiguous trust policies. If downstream parsers (LLM, reviewers) map tag names to trust levels, `<wiki_page_body>` and `<untrusted_source>` may be treated with different semantics than `<wiki_context>`. Capping content under one tag while leaving an alternative tag's content uncapped silently fragments the defense. The orchestrator's use of `<untrusted_source>` is not a `wrap_wiki_context()` call, suggesting it may be pre-cycle-72 legacy code operating under a different (possibly weaker) security model.

**Recommendation:** Document the fence-tag policy: are `<wiki_page_body>` and `<untrusted_source>` pre-cycle-72 legacy, or in-scope? If legacy, confirm they don't share the same injection surface. If in-scope, unify to use `wrap_wiki_context()` or clarify why different tags are intentional and how downstream consumers enforce the semantic boundary.

---

### F-4: [MEDIUM] Monkeypatching fragility from attribute-form imports

**Where:** `tests/test_cycle71_wrap_extensions.py:20-24` (inherited pattern); `src/kb/lint/semantic.py:1-23` (import lines)

**Risk:** The lock-in test pattern uses `monkeypatch.setattr(kb.<module>, "wrap_wiki_context", identity_func)` to replace the imported binding in each module's namespace. This only works if the production code imports via direct form: `from kb.utils.text import wrap_wiki_context`. If semantic.py or any sibling uses the attribute form `from kb.utils import text; text.wrap_wiki_context()`, the monkeypatch intercepts the wrong binding and the test passes even though the real wrapped call never ran. This is cycle-24 L1 / cycle-16 L2 pattern risk — the test appears to be valid but never reaches the production code path.

**Recommendation:** Verify all 5 production call sites use `from kb.utils.text import wrap_wiki_context` (direct import). If any use attribute form, either refactor the import or modify the monkeypatch to intercept at the module level where the call occurs (e.g., `monkeypatch.setattr('kb.utils.text', 'wrap_wiki_context', identity_func)` and verify the call is reached).

---

### F-5: [LOW] `_FENCE_OVERHEAD` constant test is a definition-tautology

**Where:** `src/kb/utils/text.py:386-393` (constant definition); `tests/test_cycle71_wrap_extensions.py` — AC07 (pending)

**Risk:** The overhead constant is computed at import time from the same `_WIKI_CONTEXT_ASSERTION` text that the test assertion will measure. Any change to the assertion sentence (e.g., punctuation, whitespace) updates the constant automatically, so the test comparing constant to assertion will always agree by construction. No independent measurement validates that the actual rendered fence matches the expected overhead. Future edits to the assertion text will shift the constant without triggering a test failure, drifting the real budget cap silently.

**Recommendation:** Cycle-72 AC07 test should independently render `wrap_wiki_context("test_string")` and MEASURE the actual overhead at runtime, comparing it to the constant. This decouples the test from the definition and catches drift when the assertion sentence is edited later.

---

## Summary Table

| ID | Severity | Category | Exploitability | Recommendation |
|----|-----------|----|--------|--------|
| F-1 | HIGH | Scope gap | Same-class peer unprotected | Add completeness context cap or justify omission |
| F-2 | HIGH | Test design | Pipeline not exercised end-to-end | Build full dataflow test with oversized content |
| F-3 | MEDIUM | Architecture | Tag semantic drift | Unify fence policy or document boundaries |
| F-4 | MEDIUM | Test fragility | Import-alias monkeypatch bypass | Verify direct imports or fix monkeypatch form |
| F-5 | LOW | Test validity | Tautological assertion | Measure overhead independently at runtime |

---

## Verdict

```
DESIGN-EVAL-R2: BLOCK
```

**Rationale:** The design proposal introduces exploitable gaps that the R1 reviewer will likely miss due to focus on individual ACs rather than structural consistency. Specifically:
- **F-1 (HIGH):** Same-class peer left unhardened creates asymmetric injection surface.
- **F-2 (HIGH):** Non-atomic test design may pass with only half the pipeline capped.
- **F-3–F-5 (MEDIUM/LOW):** Architectural inconsistencies and test-validity issues that will surface as regressions post-merge.

**Action:** Address F-1 and F-2 as blockers. F-3–F-5 should be fixed before approval to reduce technical debt and ensure test reliability.

---

**Generated by:** DeepSeek V4 Pro (deepseek-v4-pro)  
**Cross-family check:** Opus R1 reasoning vs. DeepSeek R2 adversarial scan
