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

### HIGH

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

### MEDIUM

**Lint**
- `lint/checks.py` `check_source_coverage` first `read_text()` loop has no error handling; one unreadable file aborts the entire lint run
- `lint/checks.py` `check_source_coverage` suffix-based reference matching (`ref.endswith(f"/{f.name}")`) can false-positive on same-named files across subdirs
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

### LOW

**Docs**
- `CHANGELOG.md` `[Unreleased]` section contains committed fixes not assigned to a version — clarify whether they target v0.9.12 or backfill v0.9.11; consider adding `<!-- target: vX.Y.Z -->` comment so automation knows where to land new entries
