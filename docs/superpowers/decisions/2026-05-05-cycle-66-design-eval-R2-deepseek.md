# Cycle 66 — Design Eval R2 (DeepSeek V4 Pro)

**Date:** 2026-05-05
**Branch:** feat/cycle-66
**Step:** 4 of 24 (Round 2 of 2 — parallel with R1 Opus)
**Reviewer:** DeepSeek V4 Pro (cross-family adversarial)
**Inputs:** requirements.md, threat-model.md, brainstorm.md

---

## Analysis

Per cycle-3 L7, step through each AC's design options and score against four axes:
1. **Behavioral preservation** — post-AC, do all current callers see equivalent behavior?
2. **Test coverage** — divergent-fail proof; no source-scan tests; closes relevant threat.
3. **Implementation effort** — Step-9 LOC + complexity.
4. **Future-proofing** — does the choice age well? Does it lock the cycle into hazards?

---

## Per-AC Verdicts

### AC1 — Remove dead `__getattr__("PROJECT_ROOT")` branch

**Brainstorm lean:** Option A (delete)

**R2 recommendation:** CONFIRM Option A

**Rationale:** Branch is provably dead (PEP 562 only fires when attribute NOT in module dict; line 107 binds `PROJECT_ROOT`). Signature-preserving. All three access patterns remain equivalent.

**Behavioral preservation:** ✓

**Test coverage:** ✓ Monkeypatch + divergent-fail control (replace __getattr__ with raise).

**Implementation effort:** ~10 LOC. Trivial.

**Future-proofing:** ✓

**Risks missed:** None.

**Step-5 conditions:** None.

---

### AC2 — Expand scrub keys to `CLI_BACKEND_ENV_INJECT`

**Brainstorm lean:** Option A (module-level frozenset)

**R2 recommendation:** CONFIRM Option A, WITH TEST-SOURCING FIX

**Rationale:** T2 (argv leak) is real and valuable. Option A is simpler than Option B.

**CRITICAL GAP:** Requirements say parametrize over `_SCRUB_KEYS` literal. Threat model T4 mitigation says parametrize over `kb.config.CLI_BACKEND_ENV_INJECT.values()` (canonical source). These differ.

If parametrize over `_SCRUB_KEYS` literal:
- Future hardcode-back of 6 items makes parametrize loop stay at 6 items
- No auto-expansion on new backends
- No divergent-fail on hardcode-back
- T4 mitigation silent

If parametrize over canonical map:
- Auto-expands when backends added
- Auto-fails if `_SCRUB_KEYS` hardcoded back
- Structural T4 enforcement

**Behavioral preservation:** ✓

**Test coverage:** ✓ BUT PARAMETRIZE SOURCE MUST BE CANONICAL MAP

**Implementation effort:** ~15 LOC

**Future-proofing:** ✓ if canonical-sourced

**Risks missed:** Test parametrize source alignment

**Step-5 conditions:**
1. `tests/test_cycle66_secret_scrub.py` parametrize MUST be `kb.config.CLI_BACKEND_ENV_INJECT.values()` (flattened), NOT `_SCRUB_KEYS` literal.

---

### AC3 — Cache heuristic walk-up

**Brainstorm lean:** Option B (lru_cache maxsize=8)

**R2 recommendation:** CONFIRM Option B (Option A equally valid)

**Rationale:** Both sound. Option B is battle-tested idiomatic Python.

**Behavioral preservation:** ✓

**Test coverage:** ✓ Hit-then-miss, reset, env-bypass, binding-bypass

**Implementation effort:** ~15 LOC + decorator

**Future-proofing:** ✓

**Risks missed:** None

**Step-5 conditions:** None

---

### AC4 — Consolidate walks + AST walker

**Brainstorm lean:** Option B (sibling helper)

**R2 recommendation:** DEVIATE. Recommend Option C (in-test) OR Option B with mandatory helper tests.

**CRITICAL BLOCKER:** Existing `find_imports_from` (ast_walk.py:7-40) **only handles ast.ImportFrom**, completely misses bare `import diskcache` (ast.Import). Threat model T6 explicitly flags this.

All three options fail WITHOUT explicit coverage of BOTH import forms:
- Option A (extend): New `name=None` codepath untested
- Option B (sibling): Brand-new helper untested
- Option C (in-test): Logic localized, immediately verified. LOWER RISK.

**The AC4 negative-control is load-bearing (T6):** Fixture writes only `import diskcache` — missing `from diskcache import Cache`. If walker only handles ImportFrom, other form untested.

**Behavioral preservation:** ✓

**Test coverage:** ✗ CRITICAL GAP: must test BOTH import forms

**Implementation effort:** ~30 LOC (Option C) vs ~50 LOC (Option B + tests)

**Future-proofing:** Option B better (reusable); Option C better (no untested code)

**Risks missed:** Walker must handle both ast.Import + ast.ImportFrom; negative-control only tests one form

**Step-5 conditions:**
1. Negative-control MUST write temp files with BOTH `import {module}` (ast.Import) AND `from {module} import X` (ast.ImportFrom)
2. IF Option B chosen, mandate standalone unit tests in `tests/_helpers/test_ast_walk.py` for both import forms

---

### AC5 — Drop `allow_symlinks` kwarg

**Brainstorm lean:** Option A (delete)

**R2 recommendation:** CONFIRM Option A

**Rationale:** Kwarg verified unused (1 production caller, 0 test). Removal closes T7 structurally. Subtractive safety-hardening.

**Behavioral preservation:** ✓

**Test coverage:** ✓ Signature pin + behavioral test + caller pin (belt-and-suspenders)

**Implementation effort:** ~5 LOC

**Future-proofing:** ✓

**Risks missed:** None

**Step-5 conditions:** None

---

## Cross-AC Findings

### AC2 ↔ T4 — Parametrize source mismatch

Requirements parametrize over computed `_SCRUB_KEYS` literal. T4 mitigation requires parametrize over canonical `CLI_BACKEND_ENV_INJECT.values()`. Correction: parametrize from canonical source.

### AC4 ↔ T6 — Negative-control incomplete

Fixture tests only bare `import` form, missing `from-import` form. If walker incomplete, banned imports in from-import form leak silently. Correction: test both forms.

### No Cross-AC Conflicts

No ordering hazards or dependencies detected.

---

## Tier Escalation Check

**Verdict: Tier 2 stands.** No new trust boundaries. T2 (argv leak) is additive scrub coverage only.

---

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS**

All 5 ACs sound. Brainstorm leans correct (AC1, AC3, AC5 confirmed; AC2 confirmed with test fix; AC4 deviated for test coverage). Two Step-5 conditions load-bearing:

**Step-5 Conditions (Mandatory):**

1. **AC2 parametrize:** `tests/test_cycle66_secret_scrub.py` MUST parametrize over `kb.config.CLI_BACKEND_ENV_INJECT.values()` (canonical), NOT `_SCRUB_KEYS` literal. Forces auto-expansion, divergent-fail on hardcode-back (closes T4).

2. **AC4 negative-control:** `tests/test_cycle66_cve_greps_consolidated.py` MUST test BOTH `import {module}` (ast.Import) AND `from {module} import X` (ast.ImportFrom) forms. Assert both in result dict (closes T6). If Option B, mandate standalone helper unit tests.

---

## BLOCKERs / MAJORs / NITs

**MAJORs:**

1. **AC4 walker completeness:** Must handle both ast.Import and ast.ImportFrom
2. **AC2 parametrize drift:** If parametrize `_SCRUB_KEYS` literal, T4 mitigation silent

**NITs:**

1. AC3: Both Option A/B acceptable
2. AC4: Option B viable IF helper tests provided; Option C safer for cycle 66

---

## Summary

**APPROVE-WITH-RESOLUTIONS.** Five ACs close real security gaps (T2, T4, T6, T7) without new boundaries. Two mandatory Step-5 conditions lock test sourcing/coverage gaps. Tier 2 appropriate.
