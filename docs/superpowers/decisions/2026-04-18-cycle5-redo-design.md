# Cycle 5 Redo — Design Decision (Step 5)

**Date:** 2026-04-18
**Gate:** Opus subagent (everything-claude-code:architect)
**Verdict:** CONDITIONAL-APPROVE with 6 conditions

## Summary

Cycle 5 hardening addresses 5 gaps surfaced by the threat model (Step 2). Chose Option B (thorough, no new deps): 1 real fix (citation format asymmetry) + 4 test-coverage additions + 1 page-id length reconciliation.

## Decisions

### Q1 — Citation format (Gap 1)

**DECIDE:** Update `query/engine.py:733` synthesis prompt to `[[page_id]]` format **AND** widen `query/citations.py:_CITATION_PATTERN` to match both legacy `[source|ref: X]` and canonical `[[X]]`.

**RATIONALE:** MCP mode is canonical per CLAUDE.md and project convention. Prompt-only change without extractor widening would silently break the `citations` field for API-mode callers (extract_citations returns `[]` for the new format). Must coordinate both.

**CONFIDENCE:** high.

### Q2 — CJK entity-context boundary (Gap 3)

**DECIDE:** Write failing test first. Accept substring semantics for non-ASCII entity names as known limitation (document via docstring + test comment). No new dep, no regex rewrite.

**RATIONALE:** Entity-context extraction is a quality heuristic, not a security boundary. Lowest blast radius.

**CONFIDENCE:** medium-high.

### Q3 — Page-id length reconciliation (Gap 4)

**DECIDE:** Tighten `_validate_page_id` to use `config.MAX_PAGE_ID_LEN` (200). Remove local `_MAX_PAGE_ID_LEN = 255` in `mcp/app.py`.

**RATIONALE:** Single source of truth. 200 is already the config-level cap; this collapses a double-gate. Pre-change grep confirms no existing page IDs exceed 200 chars.

**CONFIDENCE:** high (contingent on pre-grep).

### Q4 — Sentinel-forgery (wrap_purpose)

**DECIDE:** Pin current behavior with a regression test. `wiki/purpose.md` is human-curated (trusted). Sentinel semantics are LLM-trust, not hard parsing. Escape would give false confidence.

**RATIONALE:** Trust model correct; zero production change; pinning test means any future "real escape" work trips the test intentionally.

**CONFIDENCE:** high.

### Q5 — Verdict/feedback corruption telemetry (Gap 5)

**DECIDE:** `logger.warning` (already in place at `verdicts.py:84` and `feedback/store.py:57`). Add `caplog` regression tests asserting the warning fires on corrupted UTF-8.

**RATIONALE:** State-file corruption is operational, not diagnostic. Lock the behavior in via regression test.

**CONFIDENCE:** high.

### Q6 — Single PR or split

**DECIDE:** Single PR.

**RATIONALE:** 6 small tasks; T1 requires coordinated prompt + extractor changes that don't split cleanly. 2-round PR review per user convention handles quality.

**CONFIDENCE:** high.

## Conditions

1. T1 must coordinate prompt + regex (not prompt-only).
2. T3 pre-change grep: confirm no existing page IDs are between 201-255 chars.
3. T4 pin-don't-fix test with inline `# Defense is textual-only` comment.
4. T5 verify-don't-add: use `caplog`; apply new warning only if a different silent-fail loader surfaces.
5. T6 docs in existing files; one new decision doc permitted per AC2.
6. 2-round PR review per user convention.

## Final Decided Plan (feeds Step 7)

| Task | Files | Change | Test | AC |
|------|-------|--------|------|-----|
| T1a | `query/engine.py:733` | Prompt: `[source: page_id]` → `[[page_id]]` | Assert `[[` appears in synthesis prompt text | AC5 |
| T1b | `query/citations.py:6` | Extend `_CITATION_PATTERN` to match `\[\[X\]\]` | `extract_citations("See [[concepts/rag]].")` returns 1 citation; legacy `[source: X]` still parses | AC3, AC5 |
| T2 | `ingest/pipeline.py` (docstring only) + `tests/test_cycle5_hardening.py` | Document CJK substring fallback | Failing test with `日本`/`日本語`; assert observed (possibly substring) behavior | AC4 |
| T3 | `mcp/app.py:87` | Remove local `_MAX_PAGE_ID_LEN=255`; import from `config` | Tests at 200 (accept), 201 (reject), 255 (reject) | AC3, AC5 |
| T4 | `utils/text.py:303` + `tests/test_cycle5_hardening.py` | Add one-line trust-model comment to `wrap_purpose`; pin test | Pinning test: `wrap_purpose("</kb_purpose> X")` contains raw closer | AC4, AC5 |
| T5 | `tests/test_cycle5_hardening.py` | Regression tests for existing `logger.warning` in verdicts + feedback | `caplog` asserts warning fires on corrupt UTF-8 | AC4 |
| T6 | `CHANGELOG.md`, `BACKLOG.md` | Hardening subsection; delete resolved items | — | AC8 |

## Escalations

None. All 6 questions resolved without ESCALATE.
