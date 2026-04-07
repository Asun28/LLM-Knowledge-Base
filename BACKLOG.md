# Backlog

## Phase 3.92 (known issues)

**(none — all items resolved in v0.9.11)**

## Phase 3.93 (code review 2026-04-08 — new findings)

### Security / Path Traversal

- `mcp/quality.py` `kb_refine_page` missing `_validate_page_id()` before file write — only write-capable MCP tool without traversal protection
- `review/refiner.py` `page_id` not validated against `wiki_dir` at library level before constructing write path
- `review/context.py` `page_id` not validated before `page_path.read_text()` call in `pair_page_with_sources`
- `mcp/quality.py` `kb_affected_pages`, `kb_save_lint_verdict`, `kb_lint_consistency` (comma-split ids) missing `_validate_page_id()` per-element

### MCP Error Handling

- `mcp/core.py` `kb_ingest_content` writes raw file to disk before validating extraction JSON — leaves orphaned file on validation failure
- `mcp/core.py` `kb_save_source` `OSError` from `write_text` escapes unhandled to MCP client
- `mcp/core.py` `kb_query` API branch (`query_wiki()` call) has no `try/except` — `LLMError`/timeout escapes to MCP client
- `mcp/core.py` `kb_save_source` silently overwrites existing raw source files (unlike `kb_create_page` which errors)

### Lint Correctness

- `lint/runner.py` filter key mismatch: `"dead_links"` (filter) vs `"dead_link"` (issues) — `--fix` never removes fixed errors from report (always-broken since introduction)
- `lint/checks.py` `check_source_coverage` first `read_text()` loop has no error handling; one unreadable file aborts the entire lint run
- `lint/checks.py` `check_source_coverage` suffix-based reference matching (`ref.endswith(f"/{f.name}")`) can false-positive on same-named files across subdirs
- `lint/semantic.py` two unguarded `read_text()` in `_group_by_term_overlap` (line 166) and `build_consistency_context` (line 242)
- `lint/verdicts.py` `load_verdicts` silently discards all verdict history on `JSONDecodeError` with no warning logged

### Query Correctness

- `query/engine.py` `query_wiki` never forwards `max_results` to `search_pages` — the [1,100] clamp in `kb_query` is a dead letter in API mode
- `query/engine.py` skip-and-continue context assembly can silently exclude highest-ranked page (too large) while including lower-ranked pages

### Ingest Correctness

- `ingest/pipeline.py` summary page always overwritten without checking existence — unlike entity/concept pages which correctly use `_update_existing_page`; loses original `created:` date on re-ingest
- `ingest/pipeline.py` no defense-in-depth path traversal guard: `ingest_source` never verifies `source_path` resolves inside `RAW_DIR` (only MCP layer validates)
- `ingest/pipeline.py` `_update_sources_mapping` and `_update_index_batch` silently no-op when files missing on fresh install (no creation, no warning)

### Compile Correctness

- `compile/linker.py` `inject_wikilinks` case mismatch — `target_page_id` not lowercased before `in existing_links` check; `extract_wikilinks` always lowercases, so mixed-case page IDs are never matched as already-linked → duplicate wikilinks injected
- `compile/compiler.py` `find_changed_sources` writes manifest side-effect (saves updated template hashes) even when called read-only from `kb_detect_drift` — suppresses real template changes from next compile scan
- `compile/extractors.py` `load_template` LRU cache never invalidated mid-session — template changes during a running compile are silently ignored

### Graph / Evolve

- `graph/export.py` Mermaid label sanitization incomplete — newlines (`\n`) and backticks not stripped; LLM-generated title with newline breaks Mermaid output

### LLM Client

- `utils/llm.py` `range(MAX_RETRIES)` yields max 2 retries for `MAX_RETRIES=3` — variable named MAX_RETRIES implies first call + 3 retries; behavior gives first call + 2 retries
- `utils/llm.py` `last_error` is `None` on exhaustion path if `MAX_RETRIES=0` — `raise LLMError(...) from None` silently swallows exception chain

### Utils / Architecture

- `utils/pages.py` imports `page_id` from `graph/builder.py` — fragile coupling pulls `networkx` into every page-load operation; broken networkx import disables `load_all_pages` system-wide
- `utils/pages.py` `raw_content` field stores pre-lowercased text — name implies verbatim content; callers expecting original text get silently downcased version
- `MAX_FEEDBACK_ENTRIES` (`feedback/store.py:9`) and `MAX_VERDICTS` (`lint/verdicts.py:9`) defined as module constants, not in `kb.config` alongside `MAX_REVIEW_HISTORY_ENTRIES`

### CLI

- `cli.py` `mcp` command missing `try/except` — raw Python traceback shown on startup failure (all other CLI commands handle exceptions cleanly)

### Review Layer

- `review/refiner.py` frontmatter regex only matches LF line endings (`---\n`) — CRLF files on Windows silently fail with "Invalid frontmatter format" error
- `review/context.py` `source_path.read_text()` unguarded — `OSError`/`PermissionError` escapes caller

### CRITICAL — new blockers (from 10-part parallel code review, 2026-04-08)

- `compile/compiler.py` `load_manifest` propagates raw `json.JSONDecodeError` to all callers — one corrupt `.data/hashes.json` crashes `compile_wiki`, `find_changed_sources`, and `detect_source_drift` with no recovery (fix: return `{}` on decode error)
- `ingest/pipeline.py:273` LLM-extracted context strings containing `## References` double-inject the section header via `content.replace("## References", f"{ctx}\n\n## References", 1)`

### HIGH — additional reliability/correctness warnings

- `utils/llm.py` `call_llm_json` returns first `tool_use` block without verifying `block.name == tool_name`; wrong-tool response silently returned to caller
- `query/engine.py:131` `_build_query_context` returns `""` when ALL matched pages individually exceed the 80K limit; `query_wiki` then calls LLM with zero context and produces hallucinated answers (query engine docstring also lies — says "trimmed" but code skips pages entirely)
- `lint/verdicts.py` `load_verdicts` catches `JSONDecodeError` but does not validate parsed value is a `list`; a `{}` verdict file causes `AttributeError: 'dict' object has no attribute 'append'` in `add_verdict`
- `inject_wikilinks` `\b` regex failure is bidirectional — fails for TRAILING non-word chars too (not just leading as backlog documents); titles like `C++`, `ASP.NET`, `(RAG)` all produce zero injections silently
- `lint/semantic.py` `build_fidelity_context` and `build_completeness_context` have no context size limit; large raw sources (books, arXiv PDFs) overflow the LLM context window — query engine solved this with 80K cap, semantic module has no equivalent
- `review/context.py:63` `source_path.read_text(encoding="utf-8")` called unconditionally on any source in frontmatter; PDF, image, or non-UTF-8 files crash `kb_review_page` and `kb_lint_deep` with `UnicodeDecodeError`
- `lint/semantic.py` `_group_by_wikilinks` adds all neighbors to `seen` set; pages in link chains (A→B→C) are consumed by A's group then skipped — B and C never form valid consistency groups
- `utils/markdown.py` `extract_raw_refs` regex `[\w/.-]+` allows `../` path traversal patterns; inconsistent with `extract_citations` which explicitly rejects `..`
- `evolve/analyzer.py:60-65` `find_connection_opportunities` reads full file content including YAML frontmatter; structural keywords (`source`, `stated`, `confidence`, `created`) pass `len > 4` filter and produce false-positive link suggestions, especially in small wikis
- `utils/wiki_log.py` file creation uses `exists()` + `write_text()` — not atomic; concurrent MCP calls can race and overwrite a partially-written log with just the header (fix: use `open(path, "x")` with `FileExistsError` guard)
- `graph/builder.py` `betweenness_centrality` in `graph_stats` is unguarded and O(V·E); can stall the synchronous `kb_evolve` MCP tool for tens of seconds on large wikis (PageRank is guarded, centrality is not)
- `feedback/store.py` `page_scores` dict grows unbounded; only `entries` list is capped at 10k; every `add_feedback_entry` serialises the full scores dict regardless of wiki size
- `mcp/quality.py:371` `kb_create_page` writes `source_refs` verbatim to frontmatter without traversal validation; `../../etc/passwd` as a source ref is silently stored
- `review/refiner.py:83-96` page file written before audit trail persisted; crash between the two leaves page updated but no history entry (fix: persist history first, then write page)

### MEDIUM — additional quality items

- `cli.py` `--type` choices list missing `comparison` and `synthesis` (both valid in `PAGE_TYPES` and have extraction templates); users cannot pass these types via CLI
- `cli.py` `query`, `compile`, and `mcp` commands have zero test coverage; CLI-level failures go undetected
- `config.py` env override model IDs not validated at startup; `CLAUDE_WRITE_MODEL=""` passes empty string silently to Anthropic API (error only surfaces at call time)
- `lint/checks.py:189` `check_staleness` silently skips pages where YAML-parsed `updated` field is a quoted string rather than `datetime.date`; those pages are never flagged for staleness
- `graph/export.py` entire module (112 lines: `export_mermaid`, `_sanitize_label`, pruning, deduplication) has zero test coverage in `test_graph.py`
- `lint/checks.py` orphan detection exempts `summaries/` but not `comparisons/` or `synthesis/` pages; these are equally valid entry points and generate noise when flagged as orphans
- `query/engine.py:75` `search_pages` `max_results` not clamped inside the function; direct Python callers passing `-1` get all-but-last result (MCP layer clamps but internal callers are unprotected)
- `graph/builder.py` vs `evolve/analyzer.py` — "orphan" defined differently: `analyze_coverage` uses no-backlinks, `graph_stats` uses in_degree=0 AND out_degree>0; isolated nodes appear in one list but not the other, giving contradictory signals to callers combining both outputs
- `utils/pages.py:14` `WIKI_SUBDIRS` hardcodes subdirectory names instead of deriving from config constants; adding a new page type subdir without updating this tuple causes `load_all_pages` to silently miss it
- `evolve/analyzer.py:228` `except Exception: pass` in `generate_evolution_report` too broad; real bugs in `get_flagged_pages` are swallowed with no log output (should at least `logger.debug`)
- `feedback/reliability.py:31` `get_flagged_pages` docstring says "below threshold" but code uses `<=`; pages at exactly `LOW_TRUST_THRESHOLD` are flagged but the docstring misleadingly implies they are not
- `mcp/browse.py` `kb_search` and `kb_list_pages` missing outer `try/except` (same backlog pattern as `kb_read_page`/`kb_list_sources` but not yet documented); `kb_list_sources` also calls `f.stat()` inside its loop with no error handling — deleted file between `glob()` and `stat()` propagates `OSError` out of the entire function
- `mcp/app.py` `_format_ingest_result` dict-branch for `affected` is dead code since v0.5.0 (pipeline returns flat `list[str]`); backlink vs shared-source distinction is silently lost in the `~ ` prefix output
- `mcp/core.py` `kb_compile_scan(incremental=False)` full-scan branch (`scan_raw_sources()` path) has zero test coverage; only the incremental=True path has tests
