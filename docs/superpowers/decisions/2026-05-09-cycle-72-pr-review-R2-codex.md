# Cycle 72 — PR Review R2 (Codex GPT-5)

**Date:** 2026-05-09
**Reviewer:** Codex / GPT-5 via `codex:codex-rescue`
**Anchor commit:** `a19a7c6` (post R1-fix)
**Mode:** Cross-vendor R2 paired with Sonnet R2

> Codex sandbox blocked its own Write tool; primary session transcribed Codex's structured verdict into this canonical file per cycle-20 L4 manual-verify pattern.

---

## Findings

### MAJOR (3 BLOCKERS)

- **M-1 — AC01/AC04 cap-math overshoots reserved budget by truncation-marker length.**
  Where: `src/kb/lint/semantic.py` `_cap_page_content` + `build_consistency_context` truncation block.
  Risk: The cap reserves `_FENCE_OVERHEAD` (subtracts it from the input cap), but appends the marker `"\n…[truncated for context budget]"` AFTER slicing. Returned length = `max_chars + len(marker)`. After the cycle-71 outer `wrap_wiki_context`, total = `QUERY_CONTEXT_MAX_CHARS + len(marker)` — exceeds `QUERY_CONTEXT_MAX_CHARS`. Same issue at `build_consistency_context:402-406` (truncation marker appended after cap-slice).
  Fix: reserve marker-length in the cap calculation: `text[:max_chars - len(marker)] + marker` so total stays at `max_chars`.

- **M-2 — AC06 position assertion is presence-via-find, not strict endswith.**
  Where: `tests/test_cycle72_wrap_extensions.py::TestAC01_FidelityPageContentCap::test_oversized_page_truncated_with_marker`.
  Risk: The R1-fix asserts `marker_idx > page_heading_idx` AND `sources_separator_idx > marker_idx`. This catches "marker not in page region" but does NOT catch "marker appears mid-region, page body continues, then sources start". A regression where the cap-helper appends marker mid-string would pass.
  Fix: extract the page-body slice between `## Wiki Page` and the next `\n---\n`, then assert `page_body.rstrip().endswith(marker)`.

- **M-3 — AC09 auto-mode test asserts presence not count for 2-page fixture.**
  Where: `tests/test_cycle72_wrap_extensions.py::TestAC04_ConsistencyContextMigration::test_auto_mode_caps_page_content`.
  Risk: Fixture creates 2 pages sharing `raw/articles/shared.md`. Both bodies are oversized (`_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS + 200`). Both should be capped → 2 truncation markers. Both should be wrapped → 2 `<wiki_context>` open tags. Current test only asserts presence (`in out`). A regression where only the FIRST page's marker fires would pass. Same for fence-balance.
  Fix: assert `out.count(f"[Truncated at {_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS} chars") == 2` AND `out.count("<wiki_context>") == 2 == out.count("</wiki_context>")` (R2-F4 fence-balance).

### MINOR / NIT

- N-1: Trial telemetry note — Codex sandbox blocked its own Write tool; this is the second consecutive cycle (cycle-71 R2 DeepSeek had the same hook block) where a vendor-restricted reviewer cannot persist its own verdict file. Cycle-73+ skill-patch candidate: pre-create review-file shells primary-session-side.

## R1-fix verification

| R1 finding | Fix landed at `a19a7c6`? | Fix correct? |
|---|---|---|
| DeepSeek M-2 (AC06 position-assert) | Yes | PARTIAL — see R2 M-2; needs strict endswith |
| Sonnet M-1 (AC09 auto-mode) | Yes | PARTIAL — see R2 M-3; needs count assertions |
| Both (option (b) deviation) | Yes — addendum landed | OK |
| DeepSeek M-1 (option (a)/(b)) | Subsumed by addendum | OK |
| DeepSeek M-3 (BACKLOG in PR) | False positive in R1 | Verified correct (BACKLOG is in PR) |

## Same-class peer scan post-R1-fix

```
$ grep -rnE '<wiki_(page_body|context)>|<raw_source_|<untrusted_source>' src/kb/ --include="*.py"
```

Only `<wiki_context>` literals in `kb.utils.text` primitive definitions + cycle-70/71 docstring references. ZERO `<wiki_page_body>` / `<raw_source_N>` / `<untrusted_source>` outside docstrings/comments. Same-class peer scan PASS.

## Verdict

```
PR-REVIEW-R2-CODEX: BLOCK (3 MAJOR)
```

**Rationale:** All 3 MAJORs are in newly-introduced or R1-fix code paths, not pre-existing issues. Each has a clear surgical fix (≤5 LoC each).

**Confidence:** HIGH — cap-math overshoot is verifiable arithmetically; endswith vs find-index is a strict cycle-24 L1 read; count assertions catch single-page regressions in a multi-page fixture.

**Action:** Apply 3 fixes; re-verify with `python -m pytest tests/test_cycle72_wrap_extensions.py -v`; the fixes are non-overlapping with prior R1 changes.
