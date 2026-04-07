# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

<!-- CHANGELOG FORMAT GUIDE
## [version] — YYYY-MM-DD (Phase X.Y)

### Added      — new features, tools, modules, test files
### Changed    — behavior changes, refactors, performance improvements
### Fixed      — bug fixes
### Removed    — deleted code, deprecated features
### Stats      — test count, tool count, module count (one line)

Rules:
- One bullet per change, start with the module/file affected in backticks
- Newest release at the top
- Keep bullets concise — what changed and why, not how
-->

## [Unreleased]

### Fixed
- `mcp/browse.py`: simplified `except (OSError, PermissionError)` → `except OSError` in `kb_read_page` and `kb_list_sources` (`PermissionError` is a subclass of `OSError`)
- `scripts/hook_review.py`: added `VALID_MODES` guard (fail-open on unknown mode); `_get_diff` now checks `returncode` and surfaces stderr on `git diff` failure; prints warning when diff is silently truncated at `MAX_DIFF_CHARS`

### Removed
- `docs/superpowers/specs/2026-04-06-phase2-multi-loop-quality-design.md`: deleted obsolete Phase 2 design spec (fully implemented as of v0.6.0)

---

## [0.9.11] — 2026-04-08 (Phase 3.92)

9-item backlog hardening. All Phase 3.92 known issues resolved. Ruff clean.

### Added
- `config.py`: `MAX_REVIEW_HISTORY_ENTRIES = 10_000` and `VERDICT_TREND_THRESHOLD = 0.1` constants

### Changed
- `compile/linker.py`: `inject_wikilinks` uses smart lookahead/lookbehind for titles starting/ending with non-word chars (`C++`, `.NET`, `GPT-4o`)
- `compile/compiler.py`: `compile_wiki` now propagates `pages_skipped`, `wikilinks_injected`, `affected_pages`, `duplicates` from ingest result; `kb_compile` MCP output shows these fields
- `lint/checks.py`: `check_staleness` narrows `except Exception` to specific types; `check_source_coverage` merged into single-pass loop (reads each file once via `frontmatter.loads()`)
- `lint/trends.py`: hardcoded `0.1` trend threshold replaced with `VERDICT_TREND_THRESHOLD` config constant
- `utils/wiki_log.py`: `stat()` result cached — called once instead of twice
- `README.md`, `others/architecture-diagram.html`: corrected "26 tools" to "25 tools"

### Fixed
- `review/refiner.py`: review history now capped at `MAX_REVIEW_HISTORY_ENTRIES` (same pattern as feedback/verdict stores)
- `mcp/browse.py`: `kb_read_page` and `kb_list_sources` wrap I/O in `try/except OSError` — raw exceptions no longer escape to MCP client
- `lint/checks.py`: `fix_dead_links` only appends audit trail entry when `re.sub` actually changed content (eliminates phantom entries)
- `evolve/analyzer.py`: added module-level logger; `find_connection_opportunities` and `suggest_new_pages` guard `read_text()` with `try/except (OSError, UnicodeDecodeError)`

### Stats
- 583 tests (+9), 25 MCP tools, 12 modules

---

## [0.9.10] — 2026-04-07 (Phase 3.91)

5-agent parallel code review fix list.

### Changed
- `ingest/pipeline.py`: `inject_wikilinks` frontmatter split uses regex (`_FRONTMATTER_RE`)
- `compile/linker.py`: `resolve_wikilinks`/`build_backlinks` wrap `read_text()` in `try/except (OSError, UnicodeDecodeError)`
- `ingest/extractors.py`: `KNOWN_LIST_FIELDS` extended with `key_arguments`, `quotes`, `themes`, `open_questions`
- `graph/export.py`: Mermaid `_safe_node_id` tracks seen IDs with suffix deduplication
- `lint/runner.py`: `run_all_checks` with `fix=True` removes fixed issues from report
- `mcp/core.py`: `kb_ingest` wrapped in `try/except`; `kb_create_page` uses `_validate_page_id(check_exists=False)`
- `mcp/core.py`: URL in `kb_ingest_content`/`kb_save_source` wrapped in `yaml_escape()`
- `config.py`: `VERDICTS_PATH` and LLM retry constants moved from inline definitions
- `evolve/analyzer.py`: `detect_source_drift` bare `except` narrowed
- `ingest/extractors.py`: `extract_raw_refs` extended to `.csv`/`.png`/`.jpg`/`.jpeg`/`.svg`/`.gif`

### Fixed
- `compile/compiler.py`: `save_manifest` now uses `atomic_json_write`

### Stats
- 574 tests, 25 MCP tools, 12 modules

---

## [0.9.9] — 2026-04-07 (Phase 3.9)

Infrastructure for content growth and AI leverage.

### Added
- `config.py`: environment-configurable model tiers (`CLAUDE_SCAN_MODEL`, `CLAUDE_WRITE_MODEL`, `CLAUDE_ORCHESTRATE_MODEL` env vars)
- `search.py`: PageRank-blended search ranking (`final_score = bm25 * (1 + PAGERANK_SEARCH_WEIGHT * pagerank)`)
- `ingest/pipeline.py`: hash-based duplicate detection (checks compile manifest for existing sources with identical content hash)
- `kb.lint.trends`: new module — `kb_verdict_trends` MCP tool (weekly pass/fail/warning rates, quality trend direction)
- `kb.graph.export`: new module — `kb_graph_viz` MCP tool (Mermaid flowchart with auto-pruning, subgraph grouping)
- `compile/linker.py`: `inject_wikilinks()` for retroactive inbound wikilink injection
- `ingest/pipeline.py`: content-length-aware tiering (`SMALL_SOURCE_THRESHOLD=1000`)
- `ingest/pipeline.py`: cascade update detection (`affected_pages` return key)

### Fixed
- (post-review round 1) `inject_wikilinks` integrated into `ingest_source()` with lazy import; `_format_ingest_result` shows duplicate detection
- (post-review round 2) `_update_existing_page` accepts `verb` parameter — concept pages write "Discussed in" correctly; `_process_item_batch` derives `subdir` from `_SUBDIR_MAP`
- (post-review round 3) `_format_ingest_result`: `affected_pages` flat list handling; `wikilinks_injected` key now read by formatter

### Stats
- 574 tests (+56), 25 MCP tools (+2), 12 modules (+2)

---

## [0.9.8] — 2026-04-06 (Phase 3.9a)

Deep audit fixes and structured outputs.

### Added
- `utils/llm.py`: `call_llm_json()` — structured output via Claude tool_use (forced tool choice guarantees valid JSON)
- `ingest/extractors.py`: `build_extraction_schema()` + `_parse_field_spec()` for template-to-JSON-Schema conversion
- `utils/llm.py`: `_make_api_call()` shared retry helper (extracted from `call_llm`, used by both text and JSON calls)
- `utils/io.py`: `atomic_json_write()` utility (consolidated 3 identical atomic write implementations)
- `utils/llm.py`: `_resolve_model()` helper (deduplicated tier validation)

### Changed
- `ingest/extractors.py`: `load_template()` is now LRU-cached; precompiled regex in `_parse_field_spec()`
- `utils/llm.py`: removed dead 429 from `APIStatusError` retry codes (handled by `RateLimitError` catch)

### Fixed
- `mcp/core.py`: `kb_ingest` path traversal protection (validates resolved path within `PROJECT_ROOT`)
- `feedback.py`: `cited_pages` deduplicated before trust scoring (prevents inflated trust)
- `review/refiner.py`: atomic writes for review history (tempfile+rename)

### Stats
- 518 tests (+29), 23 MCP tools, 10 modules

---

## [0.9.7] — 2026-04-06 (Phase 3.8)

Tier-3 fixes and observability.

### Changed
- `query.py`: search logs debug when falling back to raw terms (all stopwords filtered)
- `mcp/health.py`: `kb_affected_pages` uses `debug` instead of `warning` for expected shared-sources failure
- `utils/llm.py`: `LLMError` messages distinguish error types (timeout, rate limit, connection, server error with status code)

### Stats
- 490 tests (+7), 23 MCP tools, 10 modules

---

## [0.9.6] — 2026-04-06 (Phase 3.7)

Tier-2 audit hardening.

### Changed
- `query.py`: context skips whole pages instead of truncating mid-page (preserves markdown structure)
- `feedback.py` / `lint/verdicts.py`: atomic writes (temp file + rename)
- `ingest/pipeline.py`: entity/concept count limits (`MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50`)

### Fixed
- `search.py`: empty query validation in `kb_search`
- `feedback.py`: citation path traversal validation (rejects `..` and leading `/`)
- `mcp/quality.py`: bare except logging in `kb_refine_page`
- `evolve/analyzer.py`: surfaces low-trust pages from feedback (`flagged_pages` in report)

### Stats
- 483 tests (+18), 23 MCP tools, 10 modules

---

## [0.9.5] — 2026-04-05 (Phase 3.6)

Tier-1 audit hardening.

### Changed
- `mcp_server.py`: MCP instructions string updated with 3 missing tools (`kb_compile`, `kb_detect_drift`, `kb_save_source`)
- `evolve/analyzer.py`: stub check logs on failure instead of silent `pass`
- `lint/checks.py`: `fix_dead_links()` writes audit trail to `wiki/log.md`

### Fixed
- `ingest/pipeline.py`: extraction data type validation (`isinstance` guard for `entities_mentioned`/`concepts_mentioned`)
- `graph/analysis.py`: `UnicodeDecodeError` handling in `build_graph()` (skips unreadable pages)
- `mcp/core.py`: empty title validation in `kb_create_page`

### Stats
- 465 tests (+13), 23 MCP tools, 10 modules

---

## [0.9.4] — 2026-04-05 (Phase 3.5)

Tier 1-3 improvements.

### Added
- `lint/checks.py`: `check_stub_pages()` — flags pages with <100 chars body, integrated into `run_all_checks()` and evolve
- `evolve/analyzer.py`: `detect_source_drift()` — finds wiki pages stale due to raw source changes
- `mcp/health.py`: `kb_detect_drift` MCP tool (23rd tool)

### Fixed
- `graph/analysis.py`: `build_backlinks()` now filters broken links (consistent with `build_graph()`)
- `evolve/analyzer.py`: `analyze_coverage()` uses `parent.name` instead of fragile string containment
- `ingest/pipeline.py`: redundant `.removesuffix(".md")` removed from evolve
- `ingest/extractors.py`: JSON fence stripping handles whitespace

### Stats
- 452 tests (+21), 23 MCP tools (+1), 10 modules

---

## [0.9.3] — 2026-04-05 (Phase 3.4)

Feature completion.

### Added
- `mcp/core.py`: `kb_compile` MCP tool (22nd tool, calls `compile_wiki()`)
- `lint/runner.py` / `cli.py`: `kb lint --fix` (auto-fixes dead links by replacing broken `[[wikilinks]]` with plain text)
- `config.py`: `MAX_SEARCH_RESULTS` constant (replaces hardcoded 100)

### Stats
- 431 tests (+17), 22 MCP tools (+1), 10 modules

---

## [0.9.2] — 2026-04-05 (Phase 3.3)

Audit fixes — 15 bug fixes across ingest, lint, query, and validation.

### Changed
- `ingest/pipeline.py`: replaced flawed regex in `_update_existing_page()` with `finditer` last-match approach; added logging to silent exception handler
- `lint/semantic.py`: removed domain terms from `common_words` stoplist; fixed consistency group truncation (chunks instead of silent discard)
- `query.py`: added context truncation logging; BM25 avgdl guard logging
- `mcp/browse.py`: case-insensitive page lookup validates resolved path stays in WIKI_DIR
- `mcp/health.py`: `logger.exception` replaced with `logger.error`

### Fixed
- `feedback.py`: length limits enforced (question/notes 2000 chars, page ID 200 chars, max 50 cited pages, path traversal rejection)
- `lint/verdicts.py`: severity validation (`error`/`warning`/`info`)
- `review/refiner.py`: rejects content starting with `---`
- `ingest/pipeline.py`: `pages_skipped` surfaced in CLI and MCP output

### Stats
- 413 tests (+31), 21 MCP tools, 10 modules

---

## [0.9.1] — 2026-04-04 (Phase 3.2)

Comprehensive audit and hardening.

### Added
- 93 new tests across 6 new test files: `test_llm.py`, `test_lint_verdicts.py`, `test_paths.py`, `test_mcp_browse_health.py`, `test_mcp_core.py`, `test_mcp_quality_new.py`

### Changed
- `utils/llm.py`: thread-safe LLM client singleton (double-check locking); `ValueError` on invalid tier
- `utils/wiki_log.py`: O(1) append (replaces O(n) read-modify-write)
- `mcp/`: consistent `_validate_page_id()` usage across all tools; confidence level validation in `kb_create_page`
- `utils/text.py`: `yaml_escape` handles `\r` and `\0`
- `feedback.py` / `lint/verdicts.py`: 10k entry retention limits

### Fixed
- `search.py`: BM25 division-by-zero fix (avgdl=0 guard)
- `ingest/pipeline.py`: source path traversal protection in `pair_page_with_sources()`
- `ingest/pipeline.py`: frontmatter-aware source collision detection in `_update_existing_page()`
- `lint/semantic.py`: duplicate "could" removed

### Stats
- 382 tests (+93), 21 MCP tools, 10 modules. MCP tool test coverage 41% to 95%.

---

## [0.9.0] — 2026-04-04 (Phase 3.1)

Hardening release.

### Changed
- `mcp/`: all tools wrap external calls in try/except; `max_results` bounds [1, 100] in `kb_query`/`kb_search`; MCP instructions updated with Phase 2 tools
- `utils/llm.py`: Anthropic SDK `max_retries=0` (double-retry fix)
- `compile/linker.py` / `graph/analysis.py`: redundant `.removesuffix(".md")` removed

### Fixed
- `mcp/`: `_validate_page_id()` rejects `..` and absolute paths, verifies resolved path within WIKI_DIR — applied to `kb_read_page`, `kb_create_page`
- `models.py`: citation regex fix (underscore support in page IDs)
- `ingest/pipeline.py`: slug collision tracking (`pages_skipped` in ingest result)
- `ingest/extractors.py`: JSON fence hardening (handles single-line `` ```json{...}``` ``)

### Stats
- 289 tests (+37), 21 MCP tools, 10 modules

---

## [0.8.0] — 2026-04-03 (Phase 3.0)

BM25 search engine.

### Added
- `search.py`: BM25 ranking algorithm replacing naive bag-of-words (term frequency saturation, inverse document frequency, document length normalization)
- `search.py`: custom tokenizer with stopword filtering and hyphen preservation
- `config.py`: configurable `BM25_K1`/`BM25_B` parameters; title boosting via `SEARCH_TITLE_WEIGHT` token repetition

### Stats
- 252 tests, 21 MCP tools, 10 modules

---

## [0.7.0] — 2026-04-02 (Phase 2.3)

S+++ upgrade.

### Added
- `kb.mcp` package: MCP server split into 5 modules from 810-line monolith (`app`, `core`, `browse`, `health`, `quality`)
- `graph/analysis.py`: PageRank and betweenness centrality
- `ingest/pipeline.py`: entity/concept enrichment on multi-source ingestion
- `lint/verdicts.py`: persistent lint verdict storage with audit trail
- `mcp/core.py`: `kb_create_page` and `kb_save_lint_verdict` tools
- `templates/`: comparison and synthesis extraction templates

### Changed
- `compile/linker.py`: case-insensitive wikilink resolution
- `feedback.py`: trust threshold boundary fix (`<` to `<=`)
- `compile/compiler.py`: template hash change detection triggers recompile

### Stats
- 234 tests, 21 MCP tools, 10 modules

---

## [0.6.0] — 2026-04-01 (Phase 2.2)

DRY refactor and code quality.

### Added
- `kb.utils.text`: shared `slugify()` (2x to 1x)
- `kb.utils.wiki_log`: shared log appending (4x to 1x)
- `kb.utils.pages`: shared `load_all_pages()` / `page_id` (3x to 1x)
- `ingest/pipeline.py`: source type whitelist validation; `normalize_sources()` for consistent list format

### Changed
- `mcp_server.py`: `_apply_extraction` (80 lines) replaced by `ingest_source(extraction=...)`
- `utils/text.py`: `yaml_escape` extended for newlines/tabs
- `utils/wiki_log.py`: auto-create `wiki/log.md` on first write
- Test fixtures consolidated (`create_wiki_page`, `create_raw_source`)

### Stats
- 180 tests (+33 parametrized edge case tests), 19 MCP tools, 10 modules

---

## [0.5.0] — 2026-03-31 (Phase 2.1)

Quality and robustness fixes.

### Added
- `feedback.py`: weighted Bayesian trust scoring (wrong penalized 2x)
- `utils/text.py`: canonical path utilities (`make_source_ref`, `_canonical_rel_path`)
- `config.py`: tuning constants (`STALENESS_MAX_DAYS`, `SEARCH_TITLE_WEIGHT`, etc.)

### Changed
- `ingest/extractors.py`: YAML injection protection; extraction JSON validation
- `models.py`: regex-based frontmatter parsing
- `graph/analysis.py`: edge invariant enforcement; empty slug guards

### Stats
- 147 tests, 19 MCP tools, 10 modules

---

## [0.4.0] — 2026-03-30 (Phase 2)

Multi-loop supervision system.

### Added
- `kb.feedback`: query feedback store with weighted Bayesian trust scoring
- `kb.review`: page-source pairing, review context/checklist builder, page refiner
- `kb.lint.semantic`: fidelity, consistency, completeness context builders for LLM evaluation
- `kb.lint.verdicts`: persistent lint/review verdict storage
- `.claude/agents/wiki-reviewer.md`: Actor-Critic reviewer agent
- 7 new MCP tools: `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`

### Stats
- 114 tests, 19 MCP tools (+7), 10 modules (+3)

---

## [0.3.0] — 2026-03-29 (Phase 1)

Initial release. Core system with 5 operations + graph + CLI.

### Added
- Content-hash incremental compile with three index files
- Model tiering (scan/write/orchestrate)
- Structured lint output
- 5 operations: ingest, compile, query, lint, evolve
- Knowledge graph with wikilink extraction
- CLI with 6 commands
- 12 MCP tools

### Stats
- 81 tests, 12 MCP tools, 7 modules
