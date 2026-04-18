# Cycle 8 — Final Decided Design (post Step-5 gate)

**Date:** 2026-04-18
**Gate verdict:** APPROVE WITH AMENDMENTS

## Amendments to requirements (bind Step 7 plan + Step 9 impl)

### AC corrections
- **AC8 target file:** `src/kb/mcp/browse.py::kb_stats` (line 316). Codex R2 verified `kb_stats` does NOT live in `health.py`. `kb_verdict_trends` remains at `mcp/health.py:176` for AC9.

### AC additions (1 new AC)
- **AC6a:** `WikiPage.from_post(post, path)` routes `metadata.get("source")` through
  `kb.utils.io.normalize_sources` (strips traversal: `..`, absolute paths) and strips
  control chars from `title` via the existing `_strip_control_chars` pattern.
  Test: pass a post with `source: ["../../../etc/passwd"]` + BIDI marks in
  `title`; assert `from_post` returns a page whose `sources` list excludes
  traversal entries and whose `title` has no control chars.

### AC clarifications (no count change — refine existing AC)
- **AC7:** nil-safety via `getattr(response, "usage", None)` then
  `getattr(usage, "input_tokens", 0)` / `output_tokens` — fallback 0 on
  missing. Emit log ONLY on the success return path.
- **AC14:** PageRank rank-list keyed on `id.lower()`; membership = UNION of
  BM25-candidate IDs and vector-candidate IDs (NOT all graph nodes); capped
  by existing `limit * 2` budget. RRF receives exactly `[bm25, vector,
  pagerank]` lists (or `[bm25, pagerank]` when vector disabled).
- **AC15:** existence check reads `contradictions.md` content INSIDE
  `with file_lock(contradictions_path):` block (T4 defense). Match is
  EXACT BLOCK (rendered header line + claim lines). If block already
  present verbatim → skip (no-op). If header present but claims differ →
  append new block as usual (preserves Codex R2 C4 — distinct same-day
  claims still recorded). Skip path emits DEBUG log with `safe_ref` +
  date only — no claim bodies (threat-model audit rule).
- **AC16 `_validate_notes`:** strips control chars + BIDI BEFORE length
  check against `MAX_NOTES_LEN`. `field_name` MUST be a compile-time
  literal at call sites (T3 CRLF-injection defense). Error format:
  `f"Error: {field_name} too long ({n} chars; max {MAX_NOTES_LEN})."`
  Length only, no body content (T2 logging rule).
- **AC11:** chunk groups by `MAX_CONSISTENCY_GROUP_SIZE` FIRST, then cap
  total emitted chunks at `MAX_CONSISTENCY_GROUPS`. INFO-log truncation
  count. Cap-AFTER-chunking bounds transport payload predictably.
- **AC12:** strip frontmatter BEFORE applying
  `MAX_CONSISTENCY_PAGE_CONTENT_CHARS`. Appended marker exactly:
  `\n\n[Truncated at {N} chars — run kb_lint_deep for full body]`.

### New tests (1 additional assertion → count stays 30 via re-allocation)
- **AC24 (refined):** INFO record's rendered message contains no substring
  from `kwargs["messages"][0]["content"][:30]` AND no substring from
  `kwargs.get("system", "")[:30]` (T8 no-leak executable assertion).
- **AC29 (refined):** spy asserts PageRank rank-list ordering matches
  `sorted(candidates, key=pagerank_scores.get, reverse=True)`; PLUS pin
  top-5 RRF output for a fixed BM25+PageRank fixture so future tuning
  of `PAGERANK_SEARCH_WEIGHT` / `RRF_K` surfaces drift at CI time
  (Opus R1 C3).

### Step-11 verification checklist additions
- **V25:** `grep tests/ -E "WikiPage\(|RawSource\("` — every instantiation
  either uses valid enum values or is wrapped in `pytest.raises(ValueError)`.
- **V26:** `grep src/ -E "WikiPage\(|from_post\("` — every non-test caller
  catches `ValueError` per CLAUDE.md "page loading loops" convention.
- **V27:** `kb_stats(wiki_dir="../..")` and `kb_verdict_trends(wiki_dir="/etc")`
  return an `Error: ...` string (traversal rejection via
  `Path.resolve().relative_to(PROJECT_ROOT.resolve())` pattern; mirror
  `kb_lint`'s implicit pattern).

## Decisions (Q_G1-Q_G11)

| # | Decision | Confidence |
|---|----------|------------|
| Q_G1 | AC8 target → `mcp/browse.py::kb_stats` | high |
| Q_G2 | Block-exact match (header + claims) for AC15 skip | high |
| Q_G3 | PageRank rank-list = UNION of BM25 + vector candidates | high |
| Q_G4 | `getattr` nil-safety with 0 fallback | high |
| Q_G5 | Strip first, then length-check (AC16) | high |
| Q_G6 | AC24 substring-absence test | high |
| Q_G7 | AC14 pinned top-5 snapshot | medium |
| Q_G8 | Chunk first, cap after (AC11) | high |
| Q_G9 | Frontmatter strip before truncation (AC12) | high |
| Q_G10 | Add AC6a (from_post normalize_sources + control strip) | high |
| Q_G11 | Add Step-11 caller-grep checkpoint V25/V26 | high |

## Final Decided Design Summary

Cycle 8 ships **30 ACs across 19 files** (plus 1 new AC6a = 31 total acceptance
criteria) as file-grouped commits on `feat/backlog-by-file-cycle8`:

- **Package surface (3):** `kb/__init__.py`, `utils/__init__.py`, `models/__init__.py`
  curated re-exports with `__all__`.
- **Models (4):** `WikiPage.__post_init__` validates enums (raises `ValueError`);
  `to_dict()` wire-format serializer; `WikiPage.from_post(post, path)` classmethod
  that ALSO routes `source` via `normalize_sources` and strips control chars from
  `title`.
- **LLM telemetry (1):** `_make_api_call` emits INFO log on success with
  `model/attempt/tokens_in/tokens_out/latency_ms`; nil-safe via `getattr`.
- **MCP wiki_dir plumbing (2):** `kb_stats` (in `browse.py`) and
  `kb_verdict_trends` (in `health.py`) accept `wiki_dir: str | None = None`.
  Both reject traversal via `Path.resolve().relative_to(PROJECT_ROOT.resolve())`.
- **Consistency caps (4):** `config.py` adds
  `MAX_CONSISTENCY_GROUPS = 20` + `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096`;
  `build_consistency_context` auto mode chunks then caps total chunks;
  per-page body truncated AFTER frontmatter strip; docstring updated.
- **PageRank rank-level (1):** `search_pages` wrapper builds PageRank rank-list
  (union of BM25+vector candidates), passes to unchanged `rrf_fusion(lists)`.
- **Contradictions idempotency (1):** `_persist_contradictions` reads inside
  `file_lock`, matches EXACT block (header + claims); skip on identical, append
  on different claims.
- **Notes validation (1):** `_validate_notes(notes, field_name)` in
  `mcp/app.py`; called from `kb_query_feedback` + `kb_refine_page`.
- **Tests (13):** one file per feature area — `test_cycle8_package_exports.py`,
  `test_cycle8_models_validation.py`, `test_cycle8_llm_telemetry.py`,
  `test_cycle8_health_wiki_dir.py`, `test_cycle8_consistency_caps.py`,
  `test_cycle8_pagerank_prefusion.py`, `test_cycle8_contradictions_idempotent.py`.

All rank/idempotency/telemetry changes go through existing concurrency
primitives (`file_lock`, `atomic_text_write`) and sanitiser helpers
(`_sanitize_error_str`, `normalize_sources`). Blast radius is contained to
the four behavior touch-points called out in the Step 2 threat model.
