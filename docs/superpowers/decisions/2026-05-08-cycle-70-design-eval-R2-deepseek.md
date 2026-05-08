# Design Evaluation Verdict — R2 DeepSeek (Adversarial)
**Cycle:** 70  
**Date:** 2026-05-08  
**Reviewer:** R2 DeepSeek  
**Result:** 2 MAJOR findings requiring primary-session action  
**Confidence:** High (all claims verified or downgraded via mandatory fact-check pass)

---

## 1. Overview
The primary session provides 16 ACs across 6 buckets, a 10-threat model, and 8 design questions with recommendations. The artifacts aim to finalize hygiene sweeps, introduce snapshot tests, audit date-contingent edge cases, uplift a fragile inspect.getsource test, and erect a prompt-injection defense boundary.

**Two MAJOR gaps exist:**
- **MAJOR-09-DATES:** The AC09 date audit risks incomplete coverage — two of four date.today() call sites in pipeline.py are not exercised by the existing _FakeDate monkeypatch test, threatening snapshot determinism.
- **MAJOR-11-INTS:** AC11 lacks an explicit enumeration of code locations that must integrate wrap_wiki_context(). Without that mapping, AC12 lock-in tests cannot guarantee full boundary coverage, leaving open a prompt-injection bypass (Threat T2).

All other requirements are sound, with minor remarks on test robustness and design details.

---

## 2. Findings by Requirement Bucket

### 2.1 Bucket A — BACKLOG Hygiene
**AC01–AC04** verified:
- `pyproject.toml:30` – httpx pin present.
- `README.md:137-148` – KB_PROJECT_ROOT export instruction exists.
- `src/kb/query/hybrid.py:19` and `src/kb/compile/compiler.py:624` – KB_STRICT_PUBLISH references confirmed.
- `tests/test_lint_query_fixes_v092.py:276` – only a docstring mention for inspect.getsource; no function-call hits.

**AC05** lock-in test prevents re-insertion.  
**Risk:** The test may rely on primitive string-search of a Markdown BACKLOG file. If the check is too brittle (exact match vs. regex), an adversarial re-addition with whitespace/rephrasing could bypass. **MINOR** — easily hardened.

### 2.2 Bucket B — Snapshot Subjects
**AC06–AC08** production functions exist:
- `pipeline.py:408` _build_summary_content
- `publish.py:209` build_llms_full_txt
- `publish.py:290` build_graph_jsonld

**Risk:** Determinism must cover timestamps, random seeds, dict ordering. The shared fixture strategy is appropriate, but must audit each for non-deterministic sources. **MINOR** — standard snapshot discipline.

### 2.3 Bucket C — AC09 Date-Contingent Audit (MAJOR-09-DATES)
**Requirement:** "Audit cycle-69 AC14 for date-contingent edge case. Verify _FakeDate monkeypatch covers all pipeline.py date.today() call sites."

**State evidence:**
- `pipeline.py` contains four date.today() call sites: lines **207, 216, 351, 664**.
- `test_cycle69_snapshots.py:79-98` patches pipeline.date with _FakeDate(2026-05-08).
- The test **only exercises lines 207, 216** (inside _persist_contradictions). Lines **351** (_check_fresh_source) and **664** (_record_initial_metadata) are **not called**.

**MAJOR Gap:** If snapshot tests invoke _check_fresh_source or _record_initial_metadata, dates will be uncontrolled. This violates AC14's determinism guarantee and enables Threat T-8.

**Required Action:** Extend AC09 audit to cover all four date.today() call sites with deterministic assertions.

### 2.4 Bucket D — AC10 Spy Upgrade
**AC10:** Replace inspect.getsource in test_compile.py:217 with spy/stub verifying both call sites of _canonical_rel_path.

**Current test** (lines 224-231, 235) checks source substrings.  
**Risk:** Spy must assert actual invocations. If test doesn't execute both functions, one site could regress silently. **MINOR** — parametrized tests mitigate per Q6.

### 2.5 Bucket E — Prompt-Injection Boundary (MAJOR-11-INTS)
**AC11:** Create wrap_wiki_context() helper in src/kb/query/prompt_safety.py with fence, escape sanitization (T3), empty-content handling (T4).  
**AC12:** Lock-in tests ensuring fence is always used.

**Threat T2:** "Boundary helper bypassed by future code path → AC12 lock-in + future AST guard."

**Underspecification (MAJOR):**
AC11 does **not** enumerate which production functions must invoke wrap_wiki_context(). Wiki-content-to-prompt injection points likely include:
- `pipeline._build_summary_content` (line 408)
- `publish.build_llms_full_txt` (line 209)
- `publish.build_graph_jsonld` (line 290)
- other synthesis/completion pathways.

Without an exhaustive list, AC12's lock-in cannot guarantee full coverage. A naive test checking that the helper exists somewhere leaves a gap for future bypass.

**Required Action:** Explicitly list all functions requiring wrap_wiki_context() instrumentation. AC12 lock-in tests each call site.

### 2.6 Bucket F — Documentation Artifacts
Straightforward production of artifacts. No technical risk.

---

## 3. Threat Model Coverage
T1 prompt-injection: Fence + system-prompt assertion (defense-in-depth).  
T2 helper bypassed: Partially addressed; missing integration site list weakens coverage (MAJOR-11-INTS).  
T3 escapes: Helper sanitizes.  
T4 orphan fence: Helper short-circuits.  
T5 length-cap: Design must reserve overhead. MINOR.  
T6-T7 nondeterminism: Shared fixture + deterministic mocks.  
T8 date relocation: Not fully mitigated; untested sites vulnerable (MAJOR-09-DATES).  
T9 spy completeness: Parametrized tests recommended (Q6).  
T10 BACKLOG re-insertion: AC05 lock-in; ensure regex resilience.

---

## 4. Brainstorm Design Questions
All primary-session recommendations sound. Q5 audit must extend to lines 351,664. Q7 must enumerate complete injection site list.

---

## 5. Fact-Check Pass (Mandatory)
All MAJOR claims verified against file:line evidence and requirement text.

### MAJOR-09-DATES
- Claim: pipeline.py lines 351, 664 use date.today() but not exercised by _FakeDate test.
- Evidence: Lines confirmed; test only exercises 207,216.
- Status: Retained as MAJOR.

### MAJOR-11-INTS
- Claim: AC11 lacks enumeration of required call sites, undermining AC12 lock-in.
- Evidence: Requirement text specifies "add wrap_wiki_context() helper + fence, AC12 lock-in tests" with no injection site mapping.
- Status: Retained as MAJOR.

---

**Final Recommendation:**
- Extend AC09 date-audit test to cover lines 351 and 664.
- Explicitly enumerate AC11 integration points; tighten AC12 lock-in scope accordingly.

With these corrections, cycle-70 design will be robust.
