# Backlog-by-File Cycle 1 — 38 Fixes Across 18 Files

**Date:** 2026-04-17
**Branch:** `fix/backlog-by-file-cycle1`
**Baseline tests:** 1649
**Pipeline:** feature-dev (threat model + design review + decision gate already run)

---

## Goal

Group open BACKLOG.md items by the file they touch (vs prior cycles that grouped by severity). Fix HIGH + MEDIUM + LOW items in a single per-file commit so each file is read/edited once.

## Scope — 38 items across 18 files

### A. `src/kb/capture.py` (6 items)

- **A1** Remove dead `slug: str` param from `_render_markdown` and all 6+ test call sites in `tests/test_capture.py`. *(Phase 5 kb-capture R3 MEDIUM)*
- **A2** Add `"maxLength": 2000` to `_CAPTURE_SCHEMA["properties"]["body"]`. *(Phase 5 kb-capture LOW)*
- **A3** Add `captures_dir: Path | None = None` keyword-only param to `capture_items` and `_write_item_files`; bind `_captures_dir = captures_dir or CAPTURES_DIR` once at function entry and use in all three bare `CAPTURES_DIR` references (`mkdir`, path construction, `os.scandir` retry). *(Phase 5 kb-capture R2 MEDIUM + R3 MEDIUM)*
- **A4** Broaden env-var secret regex in `_CAPTURE_SECRET_PATTERNS` to suffix-match: `r"(?im)^(?:export\s+)?\s*[\w]*?(API_KEY|SECRET[\w]*|PASSWORD[\w]*|TOKEN[\w]*|ACCESS_KEY|PRIVATE_KEY)[\w]*\s*=\s*\S{8,}"`. Covers `ANTHROPIC_API_KEY`, `DJANGO_SECRET_KEY`, `GH_TOKEN`, `export FOO_KEY=…`. Keeps `{8,}` value minimum to avoid false positives. *(Phase 5 kb-capture MEDIUM + 2× LOW merged)*
- **A5** Add module-level `_CAPTURES_DIR_RESOLVED: Path = CAPTURES_DIR.resolve()` immediately after the security assertion; switch `_path_within_captures` to use it. *(Phase 5 kb-capture MEDIUM)*
- **A6** Extend Authorization regex to match both Basic and Bearer: `r"(?i)Authorization:\s*(Basic|Bearer)\s+[A-Za-z0-9+/=._-]{16,}"`. *(Phase 5 kb-capture LOW)*

### B. `src/kb/lint/augment.py` + `_augment_manifest.py` + `_augment_rate.py` (5 items)

- **B1** In `run_augment`, when calling `ingest_source`, pass `raw_dir=raw_dir` so the ingest honors the augment-supplied directory. Depends on **C1**. *(Phase 5 three-round HIGH)*
- **B2** Add `data_dir: Path | None = None` to `Manifest.__init__` / `Manifest.start` / `Manifest.resume`; default to `MANIFEST_DIR`. Thread from `run_augment(data_dir=...)`. *(Phase 5 three-round MEDIUM)*
- **B3** Add `data_dir: Path | None = None` to `RateLimiter.__init__`; default to `RATE_PATH.parent`. Thread from `run_augment(data_dir=...)`. *(Phase 5 three-round MEDIUM)*
- **B4** In `run_augment`, validate `1 <= max_gaps <= AUGMENT_FETCH_MAX_CALLS_PER_RUN`; raise `ValueError` on out-of-range. Apply same validation at `cli.py lint` and `mcp/health.py kb_lint` entry points. *(Phase 5 three-round MEDIUM)*
- **B5** In `_parse_proposals_md` execute path, re-run `_url_is_allowed(url)` on each reviewed URL immediately after parsing; skip invalid URLs BEFORE calling `RateLimiter.acquire(host)`. Record blocked URLs in manifest as `blocked_by_allowlist`. *(Phase 5 three-round MEDIUM)*

### C. `src/kb/ingest/pipeline.py` (3 items)

- **C1** Add `raw_dir: Path | None = None` keyword param to `ingest_source`; pass to `detect_source_type(source_path, raw_dir=raw_dir)` and `make_source_ref(source_path, raw_dir=raw_dir)`. Path-traversal check uses supplied `raw_dir` when provided, else module `RAW_DIR`. **Blocks B1.** *(Phase 5 three-round HIGH)*
- **C2** Add `_TEXT_EXTENSIONS` (defined in `mcp/core.py:32`) enforcement inside `ingest_source` body so library-level callers cannot bypass. Import or redefine in pipeline, apply after path-traversal check. *(Phase 4.5 MEDIUM)*
- **C3** Narrow bare `except Exception` at contradiction detection (~line 759) to `(KeyError, TypeError, ValueError, re.error)`; raise unexpected exceptions. Log `logger.warning` with `source_ref` context. *(Phase 4.5 R4 HIGH)*

### D. `src/kb/ingest/extractors.py` (2 items)

- **D1** In `extract_from_source`, deepcopy the `_build_schema_cached` result before passing to `call_llm_json`: `schema = copy.deepcopy(_build_schema_cached(source_type))`. Prevents Anthropic SDK mutation poisoning subsequent calls. *(Phase 4.5 MEDIUM)*
- **D2a** Cap `purpose` text at 4KB in `build_extraction_prompt` before interpolation. Do NOT add `<kb_focus>` sentinel (deferred — new contract). *(Phase 4.5 R4 HIGH — cap-only subset)*

### E. `src/kb/ingest/contradiction.py` (1 item)

- **E1** In `_extract_significant_tokens` word-char regex, preserve length-1 tokens matching `[A-Z][+#]?` (language names: C, R, C#, C++, F#, Go, .NET). Approach: two-pass tokenize — first match `[A-Z][+#]?` tokens, then fall back to `\b\w[\w-]*\w\b` with ≥3 floor; union and apply stopword filter. *(Phase 4.5 R4 HIGH)*

### F. `src/kb/mcp/quality.py` (4 items)

- **F1** Replace `page_path.exists()` + `atomic_text_write` in `kb_create_page` with `os.open(page_path, O_WRONLY | O_CREAT | O_EXCL, 0o644)` exclusive-create + temp-file-rename pattern matching `kb_ingest_content`. On `FileExistsError` return `Error: Page already exists: {page_id}`. *(Phase 4.5 MEDIUM)*
- **F2** In `kb_refine_page`, cap `revision_notes` at `MAX_NOTES_LEN=2000`; cap `page_id` at 200 chars BEFORE path construction. Return `Error: ...` on overflow. *(Phase 4.5 MEDIUM)*
- **F3** In `kb_create_page`, after the `raw/` prefix validation loop, reject any `src` where `(PROJECT_ROOT / src).is_file()` is False. *(Phase 4.5 LOW)*
- **F4** In `kb_create_page`, cap `title` at 500 chars; strip control chars via `_strip_control_chars(title)` for parity with `page_id`. *(Phase 4.5 R4 LOW)*

### G. `src/kb/mcp/browse.py` (3 items)

- **G1** In `kb_list_sources`, replace `sorted(subdir.glob("*"))` with `os.scandir`; cap per-subdir at 500 entries; cap total response at 64KB; skip dotfiles. *(Phase 4.5 MEDIUM)*
- **G2** In `kb_search`, enforce `MAX_QUESTION_LEN` on query; include `[STALE]` marker next to score in formatted output using the existing `stale` field already emitted by `search_pages`. *(Phase 4.5 R4 HIGH)*
- **G3** In `kb_read_page`, when the case-insensitive fallback loop finds more than one match, return `Error: ambiguous page_id — multiple files match {page_id} case-insensitively: {matches}` instead of picking the first. *(Phase 4.5 R4 LOW)*

### H. `src/kb/mcp/core.py` (2 items)

- **H1** In `kb_ingest`, do `stat().st_size` pre-check against a hard cap (re-use `QUERY_CONTEXT_MAX_CHARS` as upper bound for reads). Return error without reading if oversize. *(Phase 4.5 HIGH)*
- **H2** In `kb_ingest`, validate `source_type in SOURCE_TYPE_DIRS` after the empty-string normalization branch; reject unknown types with `Error: Unknown source_type: {source_type}. Valid: {sorted list}`. *(Phase 4.5 R4 HIGH)*

### I. `src/kb/query/engine.py` (3 items)

- **I1** In `_flag_stale_results`, use `datetime.fromtimestamp(mtime, tz=timezone.utc).date()` instead of `date.fromtimestamp(mtime)`. Both sides of comparison UTC-aware. *(Phase 4.5 MEDIUM)*
- **I2** Add `(raw_dir, max_mtime)`-keyed module-level cache for `search_raw_sources` BM25 index. Invalidate by recomputing `max(p.stat().st_mtime_ns for p in raw_paths)` on each call; skip rebuild when key matches. *(Phase 4.5 MEDIUM)*
- **I3** In `rewrite_query` (or a post-call validator), reject LLM outputs containing `:`/newline, matching `^(sure|here|the standalone|okay|certainly)`i, or starting with a capital letter followed by a colon (`^[A-Z][a-zA-Z ]{0,30}:`). On reject, fall back to original `question`. *(Phase 4.5 R4 HIGH)*

### J. `src/kb/query/rewriter.py` (2 items)

- **J1** Add absolute `MAX_REWRITE_CHARS=500` (add to `kb.config`) and floor `max(3 * len(question), 120)`. Replace the bare `3 * len(question)` bound. *(Phase 4.5 MEDIUM)*
- **J2** In `_should_rewrite`, return `False` when question matches `^(who|what|where|when|why|how)\b.*\?$` case-insensitive AND contains a capitalized token. Avoids wasted scan-tier LLM calls. *(Phase 4.5 R4 LOW)*

### K. `src/kb/query/dedup.py` (1 item)

- **K1** In `_dedup_by_text_similarity`, precompute `(result, tokens)` pairs once; avoid `_content_tokens(k)` recall inside the `for k in kept` inner loop. *(Phase 4.5 MEDIUM)*

### M. `src/kb/lint/verdicts.py` (1 item)

- **M1** Add `(mtime_ns, size)`-keyed cache to `load_verdicts`; invalidate by checking `VERDICTS_PATH.stat()` on entry; rebuild on mismatch. Invalidate explicitly in `atomic_json_write` inside `add_verdict`. *(Phase 4.5 MEDIUM)*

### N. `src/kb/lint/semantic.py` (1 item)

- **N1** Replace local `re.match(r"\A\s*---\r?\n.*?\r?\n---\r?\n?(.*)", raw, re.DOTALL)` in `_group_by_term_overlap` with shared `FRONTMATTER_RE` from `kb.utils.markdown`. *(Phase 4.5 R4 LOW)*

### O. `src/kb/lint/checks.py` (1 item)

- **O1** In `check_source_coverage`, short-circuit on pages missing frontmatter fence; emit malformed-frontmatter issue instead of silently producing false-positive "Raw source not referenced" warning. *(Phase 4.5 R4 HIGH)*

### P. `src/kb/utils/markdown.py` (1 item)

- **P1** Add `_strip_code_spans_and_fences(text) -> str` helper; call in `extract_wikilinks` before `WIKILINK_PATTERN.findall`. Strips ```` ``` ```` fenced blocks, `` `…` `` inline spans, and YAML frontmatter. *(Phase 4.5 R4 HIGH)*

### Q. `src/kb/feedback/store.py` + `reliability.py` (2 items)

- **Q1** In `load_feedback`, widen except to `(json.JSONDecodeError, OSError, UnicodeDecodeError)`; log warning and return `_default_feedback()`. *(Phase 4.5 R5 HIGH)*
- **Q2** In `reliability.get_flagged_pages`, when a scores entry lacks `trust`, recompute as `(useful+1)/(useful+2*wrong+incomplete+2)` instead of defaulting to 0.5. *(Phase 4.5 R4 HIGH)*

### R. `src/kb/review/refiner.py` (1 item)

- **R1** Import `FRONTMATTER_RE` from `kb.utils.markdown`; replace local regex in `refine_page` frontmatter guard. Cap `revision_notes` at `MAX_NOTES_LEN` before `append_wiki_log`. *(Phase 4.5 R4 HIGH + R4 LOW merged)*

### S. `src/kb/utils/wiki_log.py` (1 item)

- **S1** After `except FileExistsError: pass` in `append_wiki_log`, verify `log_path.is_file()`; if directory/symlink/special-file, raise `OSError(f"Log target not a regular file: {log_path}")`. *(Phase 4.5 R5 HIGH)*

---

## Order of operations

1. **Wave 0 (pre-req):** C1 (`ingest_source(raw_dir=None)` param). Blocks B1.
2. **Wave 1 (parallel OK):** All remaining items — each file is independent.
3. **Wave 2 (verification):** pytest, ruff check, ruff format --check, MCP smoke.
4. **Wave 3 (docs):** BACKLOG.md deletions + CHANGELOG.md `[Unreleased]` entries.

## Test expectations

Create `tests/test_backlog_by_file_cycle1.py` covering:
- A3/B2/B3/C1 custom-dir kwargs route writes to supplied dirs
- A4 regex matches `ANTHROPIC_API_KEY=abcd… (8-char value)`; rejects `TOKEN_EXPIRY=3600` (shorter)
- D1 cached schema mutation in one call doesn't poison next call
- E1 contradiction tokens preserve `C`, `R`, `C++`, `.NET`
- F1 O_EXCL rejects second concurrent create
- H1 oversize file returns error without read; H2 unknown source_type rejected
- I3 rewrite prefix leaks rejected; original question falls back
- M1 verdicts cache invalidation on write
- P1 WIKILINK skips fenced blocks / inline code
- Q1 corrupt feedback JSON returns empty; Q2 missing trust key recomputes
- S1 FIFO/symlink log path raises clear OSError

## Deferred (NOT in this batch)

- D2b (`<kb_focus>` sentinel in ingest prompt) — new contract, needs downstream coordination
- B5 extra (summary counts from per-stub outcomes) — observable behavior change
- L (query/hybrid.py try/except wrapper for bm25_fn/vector_fn) — hot-path error swallow deserves dedicated PR with failure-injection tests
- All architectural items: kb.errors hierarchy, compile/compiler rename, ingest receipt file, full-compile invalidation, async MCP, log rotation, file_lock ordering
- Capture R3 CRITICAL two-pass write — deferred per R3 rating

## Risks

- **New per-file regression tests can flake** if fixture-to-implementation mapping drifts. Mitigation: assert on file artifacts AND return-dict shapes per test_phase45_high_cycle2.py pattern.
- **C1 → B1 ordering must land in one PR** to avoid partial compilation. Ensure both are in the merge commit.
- **38 items in one PR is ~2x prior cycles.** Mitigation: per-file commits let reviewer read one file at a time.
