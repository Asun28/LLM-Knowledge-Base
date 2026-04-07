# Backlog

<!-- FORMAT GUIDE — read before adding items
Each phase section groups items by severity, then by module area.
Resolved phases collapse to a one-liner; active phases list every item.

## Severity Levels

| Level      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| CRITICAL   | Data loss, crash with no recovery, or security exploit — blocks release |
| HIGH       | Silent wrong results, unhandled exceptions reaching users, reliability risk |
| MEDIUM     | Quality gaps, missing test coverage, misleading APIs, dead code |
| LOW        | Style, docs, naming, minor inconsistencies — fix opportunistically |

## Item Format

```
- `module/file.py` `function_or_symbol` — description of the issue
  (fix: suggested remedy if non-obvious)
```

Rules:
- Lead with the file path (relative to `src/kb/`), then the function/symbol.
- Include line numbers only when they add precision (e.g. `file.py:273`).
- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
- One bullet = one issue. Don't combine unrelated problems.
- When resolving an item, delete it (don't strikethrough). Record the fix in CHANGELOG.md.
- Move resolved phases under "## Resolved Phases" with a one-line summary.
-->

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11

## Phase 3.93 (code review 2026-04-08)

### CRITICAL

- `compile/compiler.py` `load_manifest` propagates raw `json.JSONDecodeError` to all callers — one corrupt `.data/hashes.json` crashes `compile_wiki`, `find_changed_sources`, and `detect_source_drift` with no recovery (fix: return `{}` on decode error)
- `ingest/pipeline.py:273` LLM-extracted context strings containing `## References` double-inject the section header via `content.replace("## References", f"{ctx}\n\n## References", 1)`

### HIGH

**Security / Path Traversal**
- `mcp/quality.py` `kb_refine_page` missing `_validate_page_id()` before file write — only write-capable MCP tool without traversal protection
- `review/refiner.py` `page_id` not validated against `wiki_dir` at library level before constructing write path
- `review/context.py` `page_id` not validated before `page_path.read_text()` call in `pair_page_with_sources`
- `mcp/quality.py` `kb_affected_pages`, `kb_save_lint_verdict`, `kb_lint_consistency` (comma-split ids) missing `_validate_page_id()` per-element
- `mcp/quality.py:371` `kb_create_page` writes `source_refs` verbatim to frontmatter without traversal validation; `../../etc/passwd` as a source ref is silently stored
- `utils/markdown.py` `extract_raw_refs` regex `[\w/.-]+` allows `../` path traversal patterns; inconsistent with `extract_citations` which explicitly rejects `..`

**MCP Error Handling**
- `mcp/core.py` `kb_ingest_content` writes raw file to disk before validating extraction JSON — leaves orphaned file on validation failure
- `mcp/core.py` `kb_save_source` `OSError` from `write_text` escapes unhandled to MCP client
- `mcp/core.py` `kb_query` API branch (`query_wiki()` call) has no `try/except` — `LLMError`/timeout escapes to MCP client
- `mcp/core.py` `kb_save_source` silently overwrites existing raw source files (unlike `kb_create_page` which errors)

**Lint Correctness**
- `lint/runner.py` filter key mismatch: `"dead_links"` (filter) vs `"dead_link"` (issues) — `--fix` never removes fixed errors from report (always-broken since introduction)
- `lint/verdicts.py` `load_verdicts` catches `JSONDecodeError` but does not validate parsed value is a `list`; a `{}` verdict file causes `AttributeError: 'dict' object has no attribute 'append'` in `add_verdict`
- `lint/semantic.py` `build_fidelity_context` and `build_completeness_context` have no context size limit; large raw sources (books, arXiv PDFs) overflow the LLM context window (fix: add 80K cap like query engine)
- `lint/semantic.py` `_group_by_wikilinks` adds all neighbors to `seen` set; pages in link chains (A→B→C) are consumed by A's group then skipped — B and C never form valid consistency groups

**Query Correctness**
- `query/engine.py` `query_wiki` never forwards `max_results` to `search_pages` — the [1,100] clamp in `kb_query` is a dead letter in API mode
- `query/engine.py:131` `_build_query_context` returns `""` when ALL matched pages individually exceed the 80K limit; `query_wiki` then calls LLM with zero context and produces hallucinated answers (fix: fall back to truncated top page)

**Ingest Correctness**
- `ingest/pipeline.py` summary page always overwritten without checking existence — loses original `created:` date on re-ingest (fix: use `_update_existing_page` like entity/concept pages)
- `ingest/pipeline.py` no defense-in-depth path traversal guard: `ingest_source` never verifies `source_path` resolves inside `RAW_DIR` (only MCP layer validates)

**Compile Correctness**
- `compile/linker.py` `inject_wikilinks` case mismatch — `target_page_id` not lowercased before `in existing_links` check; duplicate wikilinks injected for mixed-case page IDs
- `compile/compiler.py` `find_changed_sources` writes manifest side-effect (saves updated template hashes) even when called read-only from `kb_detect_drift` — suppresses real template changes from next compile scan
- `compile/linker.py` `inject_wikilinks` `\b` regex failure is bidirectional — titles with non-word chars (`C++`, `ASP.NET`, `(RAG)`) produce zero injections silently

**LLM Client**
- `utils/llm.py` `call_llm_json` returns first `tool_use` block without verifying `block.name == tool_name`; wrong-tool response silently returned to caller

**Review Layer**
- `review/context.py:63` `source_path.read_text(encoding="utf-8")` called unconditionally; PDF/image/non-UTF-8 files crash `kb_review_page` and `kb_lint_deep` with `UnicodeDecodeError`
- `review/refiner.py:83-96` page file written before audit trail persisted; crash between the two leaves page updated but no history entry (fix: persist history first, then write page)
- `review/refiner.py` frontmatter regex only matches LF line endings (`---\n`) — CRLF files on Windows silently fail with "Invalid frontmatter format" error
- `review/context.py` `source_path.read_text()` unguarded — `OSError`/`PermissionError` escapes caller

**Graph / Evolve**
- `graph/builder.py` `betweenness_centrality` in `graph_stats` is unguarded and O(V·E); can stall the synchronous `kb_evolve` MCP tool for tens of seconds on large wikis
- `evolve/analyzer.py:60-65` `find_connection_opportunities` reads full file content including YAML frontmatter; structural keywords produce false-positive link suggestions

**Utils**
- `utils/pages.py` imports `page_id` from `graph/builder.py` — fragile coupling pulls `networkx` into every page-load operation
- `utils/wiki_log.py` file creation uses `exists()` + `write_text()` — not atomic; concurrent MCP calls can race (fix: use `open(path, "x")` with `FileExistsError` guard)
- `feedback/store.py` `page_scores` dict grows unbounded; only `entries` list is capped at 10k

### MEDIUM

**Lint**
- `lint/checks.py` `check_source_coverage` first `read_text()` loop has no error handling; one unreadable file aborts the entire lint run
- `lint/checks.py` `check_source_coverage` suffix-based reference matching (`ref.endswith(f"/{f.name}")`) can false-positive on same-named files across subdirs
- `lint/semantic.py` two unguarded `read_text()` in `_group_by_term_overlap` (line 166) and `build_consistency_context` (line 242)
- `lint/verdicts.py` `load_verdicts` silently discards all verdict history on `JSONDecodeError` with no warning logged
- `lint/checks.py:189` `check_staleness` silently skips pages where YAML-parsed `updated` field is a quoted string rather than `datetime.date`
- `lint/checks.py` orphan detection exempts `summaries/` but not `comparisons/` or `synthesis/` pages; generates noise when flagged as orphans

**Query**
- `query/engine.py` skip-and-continue context assembly can silently exclude highest-ranked page (too large) while including lower-ranked pages
- `query/engine.py:75` `search_pages` `max_results` not clamped inside the function; direct Python callers passing `-1` get all-but-last result

**Ingest**
- `ingest/pipeline.py` `_update_sources_mapping` and `_update_index_batch` silently no-op when files missing on fresh install (no creation, no warning)

**Compile**
- `compile/extractors.py` `load_template` LRU cache never invalidated mid-session — template changes during a running compile are silently ignored

**Graph / Evolve**
- `graph/export.py` Mermaid label sanitization incomplete — newlines (`\n`) and backticks not stripped
- `graph/export.py` entire module (112 lines) has zero test coverage in `test_graph.py`
- `graph/builder.py` vs `evolve/analyzer.py` — "orphan" defined differently; contradictory signals to callers combining both outputs
- `evolve/analyzer.py:228` `except Exception: pass` too broad; real bugs swallowed with no log output

**LLM Client**
- `utils/llm.py` `range(MAX_RETRIES)` yields max 2 retries for `MAX_RETRIES=3` — naming implies first call + 3 retries
- `utils/llm.py` `last_error` is `None` on exhaustion path if `MAX_RETRIES=0`

**Utils / Config**
- `utils/pages.py` `raw_content` field stores pre-lowercased text — name implies verbatim content
- `utils/pages.py:14` `WIKI_SUBDIRS` hardcodes subdirectory names instead of deriving from config constants
- `config.py` env override model IDs not validated at startup; empty string passes silently to Anthropic API
- `MAX_FEEDBACK_ENTRIES` (`feedback/store.py:9`) and `MAX_VERDICTS` (`lint/verdicts.py:9`) defined as module constants, not in `kb.config`
- `feedback/reliability.py:31` `get_flagged_pages` docstring says "below threshold" but code uses `<=`

**CLI**
- `cli.py` `mcp` command missing `try/except` — raw Python traceback shown on startup failure
- `cli.py` `--type` choices list missing `comparison` and `synthesis`
- `cli.py` `query`, `compile`, and `mcp` commands have zero test coverage

**MCP**
- `mcp/browse.py` `kb_search` and `kb_list_pages` missing outer `try/except`; `kb_list_sources` `f.stat()` has no error handling
- `mcp/app.py` `_format_ingest_result` dict-branch for `affected` is dead code since v0.5.0
- `mcp/core.py` `kb_compile_scan(incremental=False)` full-scan branch has zero test coverage
