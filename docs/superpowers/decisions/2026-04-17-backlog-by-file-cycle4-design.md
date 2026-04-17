# Cycle 4 Design — Decision Gate Output

**Date:** 2026-04-17 **Branch:** `feat/backlog-by-file-cycle4`
**Verdict:** APPROVE_WITH_AMENDMENTS
**Net scope:** 22 functional items + up to 7 test-backfill items across 16 files

## Summary

Cycle 4 extends cycles 1–3's backlog-by-file cleanup. Initial 30-item design reviewed by Opus R1 (per-item source verification) + Codex R2 (edge cases, failure modes). Seven items confirmed already shipped in prior cycles; one item deferred as too architecturally deep; five rescoped.

## Q1–Q12 decisions (abbreviated — full Analysis blocks in review transcript)

| Q | Decision | Confidence |
|---|---|---|
| Q1 — Item #22 MCP surface | Pipeline-only migration + `logger.warning`; no MCP surface expansion | 0.85 |
| Q2 — Item #13 platform gate | Always reject reserved basenames (cross-platform); cap 255 chars | 0.90 |
| Q3 — Item #16 wiki-BM25 cache | Mirror `_RAW_BM25_CACHE` as `_WIKI_BM25_CACHE` | 0.85 |
| Q4 — Item #18 cache invalidation | Add `BM25_TOKENIZER_VERSION = 2` as cache-key component | 0.90 |
| Q5 — Item #19 line separators | Strip BOM + U+2028 + U+2029 silently; document invariant | 0.88 |
| Q6 — Item #20 log rotation | `log.YYYY-MM.md`; `.2`, `.3` ordinal on collision | 0.87 |
| Q7 — Item #29 title sort | Caller-side sort in `inject_wikilinks` orchestrator loop | 0.80 |
| Q8 — Item #3 citation migration | DROP — defer to dedicated Phase 4.5 atomic migration cycle | 0.92 |
| Q9 — Item #27 doc bundle | Single CLAUDE.md edit bundling stale + Phase 4.11 keys | 0.90 |
| Q10 — Shipped test backfill | Step 7 grep-audit; add items #31+ if regression tests missing | 0.82 |
| Q11 — Item #2 CJK fullwidth | Case-insensitive strip + targeted U+FF1C/U+FF1E ASCII fold in fence region | 0.78 |
| Q12 — Item #24 memory cost | Document ~150MB/5K-page profile; no runtime mitigation | 0.75 |

## Conditions (must land before Step 7)

1. DROP 7 shipped items: #4, #6, #8, #9, #10, #21, #30. Verify via grep in Step 7.
2. DROP item #3 (atomic migration too big). Add to BACKLOG.md as dedicated Phase 4.5 item.
3. Rescope #15 → CJK gate only.
4. Rescope #16 → wiki-side cache only; key `(wiki_dir, page_count, max_mtime_ns, BM25_TOKENIZER_VERSION)`.
5. Rescope #22 → pipeline-only migration + `logger.warning` on truncation.
6. Rescope #27 → stale key + Phase 4.11 output adapter keys bundled in single CLAUDE.md edit.
7. Rescope #29 → caller-side `sorted()` in orchestrator loop.
8. Item #13 BLOCKER fix: must return `"Error: ..."` (never raise), reject reserved names cross-platform, cap 255 chars, verify `kb_list_pages` surfaces existing for remediation.
9. Item #5 BLOCKER fix: partial-write path returns `"Error: ..."` string; regression test monkeypatches write failure.
10. Item #18 adds `BM25_TOKENIZER_VERSION = 2` module constant in both cache keys.
11. Item #19 sanitization invariant: strip BOM + U+2028 + U+2029 silently; document in docstring.
12. Item #20 log rotation: `log.YYYY-MM.md`, ordinal `.2` / `.3` on collision.
13. Item #2: case-insensitive strip + targeted U+FF1C/U+FF1E fold in fence-match region only.
14. Item #24: memory profile documented in module docstring; no runtime mitigation.
15. Test back-fill audit during Step 7: grep each shipped item for behavioral regression tests.
16. Dep CVE baseline: patch langsmith + python-multipart; accept diskcache no-fix in CHANGELOG.

## Final scope (22 functional items)

### ACTIVE UNCHANGED (10)
- #1 `mcp/core.py` — sweep `_rel()` on error-string path interpolations
- #7 `mcp/browse.py` — `kb_read_page` QUERY_CONTEXT_MAX_CHARS cap + truncation footer
- #11 `mcp/quality.py` — `kb_affected_pages` `check_exists=True`
- #12 `mcp/quality.py` — `add_verdict` per-issue description cap at library boundary
- #14 `mcp/health.py` — `kb_detect_drift` source-deleted third category
- #17 `query/dedup.py` — `_enforce_type_diversity` running quota
- #23 `graph/export.py` — DeprecationWarning on Path shim
- #25 `compile/compiler.py` — `_template_hashes` VALID_SOURCE_TYPES whitelist
- #26 `.env.example` — add three `CLAUDE_*_MODEL` vars
- #28 `utils/pages.py` — `load_purpose` require `wiki_dir`

### ACTIVE WITH AMENDMENTS (7)
- #2 `mcp/core.py` — strip `<prior_turn>` / `</prior_turn>` variants + control chars + targeted U+FF1C/U+FF1E fold in fence-match region only
- #5 `mcp/core.py` — `Error[partial]` string on post-create OSError (never raise)
- #13 `mcp/app.py` — Windows-reserved reject cross-platform + 255 char cap; `kb_list_pages` surfaces existing
- #18 `utils/text.py` — remove 8 overloaded quantifiers from STOPWORDS + `BM25_TOKENIZER_VERSION=2`
- #19 `utils/text.py` — strip BOM + U+2028 + U+2029 silently in sanitize helper
- #20 `utils/wiki_log.py` — `log.YYYY-MM.md` rotation with ordinal collision
- #24 `query/bm25.py` — postings-dict precompute; document memory profile

### ACTIVE RESCOPED (5)
- #15 `query/rewriter.py` — CJK-safe `len(q.strip()) < 15` short-query gate only
- #16 `query/engine.py` — wiki-side `_WIKI_BM25_CACHE` mirror
- #22 `ingest/pipeline.py` — migrate caller to `detect_contradictions_with_metadata`
- #27 `CLAUDE.md` — stale key + Phase 4.11 output adapter keys (single doc edit)
- #29 `compile/linker.py` / orchestrator loop — caller-side `sorted()`

### DROPPED-ALREADY-SHIPPED (7)
- #4 (core.py source_type whitelist), #6 (browse.py MAX_QUESTION_LEN+stale), #8 (browse.py ambiguous match), #9 (quality.py title cap), #10 (quality.py source_refs is_file), #21 (lint/checks.py missing-fence), #30 (refiner.py FRONTMATTER_RE)

### DROPPED-DEFERRED (1)
- #3 — `[source:]` → `[[page_id]]` citation migration (too large; dedicated cycle)

## Commit grouping (AC6)

~16 commits, one per file, matching cycle 3 cadence. Final commit: CHANGELOG + BACKLOG + CLAUDE.md + .env.example docs bundle.

## Proceed to Step 7 plan phase with 22-item scope + conditions above.
