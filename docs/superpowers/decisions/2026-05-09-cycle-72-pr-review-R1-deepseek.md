# Cycle 72 — PR Review R1 (DeepSeek)

## Findings

### MAJOR

**M-1: AC04 constant-resolution binding condition violated (option b used instead of option a)**
   Where: `src/kb/config.py:467-475` + `src/kb/lint/semantic.py:60`
   Risk: Design-decision C5 explicitly resolved to "OPTION (a) modify in place" but implementation chose option (b) (new constant `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS` in semantic.py) due to circular-import concern flagged during implementation. The binding condition is not met. Although functional impact is identical (effective cap is reduced by `_FENCE_OVERHEAD`), the DESIGN-DECISION condition is a gate constraint — deviations require re-approval.
   Fix: Either (i) modify constant in place per option (a) after verifying circular-import is safe OR (ii) file a cycle-72 scope-change amendment to reflect the fallback to option (b) with explicit approval.

**M-2: AC06 truncation marker assertion missing endswith check**
   Where: `tests/test_cycle72_wrap_extensions.py:111-114`
   Risk: Design-decision condition 7 ("AC06 truncation marker position assertion (endswith)") requires the test to assert that the truncation marker is at the END of the capped content. Current test uses `assert "[truncated for context budget]" in out` which checks presence only, not position. Cycle-24 L1 position-not-presence rule: without endswith assertion, a malformed cap function that appends the marker then extra content would pass the test (vacuous-test pattern).
   Fix: Add explicit endswith assertion: `assert output.endswith("\n…[truncated for context budget]")` to TestAC01_FidelityPageContentCap.test_oversized_page_truncated_with_marker.

**M-3: AC17 deferred entries unverified in PR context**
   Where: `BACKLOG.md` (grep via Step-11 verifier)
   Risk: Design-decision condition 14 requires 3 deferred entries with exact literal token `"deferred — file BACKLOG entry post-cycle-72"`. Step-14 security-verify confirms 3 hits exist in BACKLOG.md, but the PR diff does not show BACKLOG.md changes. Step-11 must verify the entries are present; if the commit that adds them is missing from the PR, this is a BLOCKER.
   Fix: Confirm AC17 commit includes BACKLOG.md edits with 3 new entries. If missing, add them before merge.

### MINOR

**M-4: AC04 comment explains fallback rationale but creates mental-model drift**
   Where: `src/kb/config.py:472-474` (comment text)
   Risk: The comment states "Design-decision condition 5 picked option (a) modify-in-place but R1 C5 flagged the circular-import risk; option (b) was the listed fallback." This implies the fallback (option b) was already documented in the design decision, but the design doc text at line 25 says "Reconciled choice: OPTION (a) modify in place" with no fallback language. Creates confusion about whether option (b) was an approved fallback or an unauthorized deviation.
   Fix: Clarify comment to cite the specific design-decision section that documents the fallback (e.g., "per design-decision.md line X"), or update design-decision.md to explicitly approve option (b) as acceptable if circular import materializes during implementation.

**M-5: Test coverage for per-page wrap assertion count (AC09) not shown**
   Where: `tests/test_cycle72_wrap_extensions.py` (TestAC04_ConsistencyContext class, not fully shown)
   Risk: Design-decision condition 7 requires "Test AC09 asserts N `<wiki_context>` open tags for an N-page group." The test snippet provided does not show this assertion. If the test doesn't verify the per-page wrap is applied N times (once per page in the 4-page fixture), the mutation control (AC14) will not catch a regression where the wrap is accidentally applied only once (outer wrap instead of per-page).
   Fix: Verify TestAC04_ConsistencyContext includes assertion like `assert out.count("<wiki_context>") == 4` for the 4-page fixture.

### NIT

**N-1: Ellipsis character encoding in marker string**
   Where: `src/kb/lint/semantic.py:47`
   Risk: The truncation marker uses Unicode ellipsis `…` (U+2026) instead of ASCII `...`. This is not a functional issue (character is correctly encoded) but may cause confusion if the marker is parsed by tools expecting ASCII. Minor readability concern.
   Fix: No action required; this matches the design-decision design intent. Document in CLAUDE.md if this character is used elsewhere for consistency.

---

## Verdict

**PR-REVIEW-R1: BLOCK (3 MAJOR)**

The PR violates 3 binding design-decision conditions:
1. **AC04 constant not modified in place per option (a)** — must be resolved before merge (either reverse to option a or get explicit approval for option b).
2. **AC06 truncation marker test missing endswith assertion** — vacuous-test risk per cycle-24 L1; add position assertion.
3. **AC17 deferred BACKLOG entries** — unverified in PR context (security-verify confirms existence, but PR merge must include the AC17 commit that adds them).

Minor findings (M-4, M-5) require clarification but are not merge-blockers if resolved via post-merge amendments (CLAUDE.md update, design-decision footnote).

**R2 will likely catch:**
- Same-class peer drift: any stray `<wiki_page_body>` / `<raw_source_N>` / `<untrusted_source>` literals outside docstrings/comments
- Vacuous-test patterns in AC08-AC15 lock-ins if mutation controls don't reach production call sites
- Atomic-coupling drift: if AC02 and AC02a are not in the same commit
- Signature drift: if `_build_pre_extract_prompt` or `_cap_page_content` callers use inconsistent import patterns

**Confidence: HIGH** — 3 MAJOR findings are binding-condition violations; design-decision text is the primary source of truth and all 3 are clear divergences or gaps.

