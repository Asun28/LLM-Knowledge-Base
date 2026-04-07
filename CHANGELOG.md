# Changelog

Full phase-by-phase development history for LLM-Knowledge-Base.

## Phase 1 (complete, v0.3.0)
Content-hash incremental compile, three index files, model tiering, structured lint output, 5 operations + graph + CLI.

## Phase 2 (complete, v0.4.0)
Multi-loop supervision for Lint, Actor-Critic compile, query feedback loop, Self-Refine on Compile. 7 new MCP tools, 3 new modules, wiki-reviewer agent.

## Phase 2.1 (complete, v0.5.0)
Quality and robustness fixes — weighted Bayesian trust scoring (wrong penalized 2x), canonical path utilities (`make_source_ref`, `_canonical_rel_path`), YAML injection protection, extraction JSON validation, regex-based frontmatter parsing, graph edge invariant enforcement, empty slug guards, config-driven tuning constants (`STALENESS_MAX_DAYS`, `SEARCH_TITLE_WEIGHT`, etc.), improved MCP error handling with logging.

## Phase 2.2 (complete, v0.6.0)
DRY refactor and code quality — shared utilities (`kb.utils.text`, `kb.utils.wiki_log`, `kb.utils.pages`) eliminated all code duplication (slugify 2x→1x, page loading 2x→1x, log appending 4x→1x, page_id 3x→1x). MCP server's `_apply_extraction` (80 lines) replaced by `ingest_source(extraction=...)`. Source type whitelist validation in extractors. `normalize_sources()` ensures consistent list format across all modules. YAML escape extended for newlines/tabs. Auto-create wiki/log.md on first write. Consolidated test fixtures (`create_wiki_page`, `create_raw_source`). 33 new parametrized edge case tests (180 total).

## Phase 2.3 (complete, v0.7.0)
S+++ upgrade — MCP server split into `kb.mcp` package (5 modules from 810-line monolith), graph analysis with PageRank and betweenness centrality, entity/concept enrichment on multi-source ingestion, persistent lint verdict storage with audit trail, case-insensitive wikilink resolution, trust threshold boundary fix (< to <=), template hash change detection for compile, comparison/synthesis extraction templates, 2 new MCP tools (`kb_create_page`, `kb_save_lint_verdict`). 21 MCP tools, 234 tests.

## Phase 3.0 (complete, v0.8.0)
BM25 search engine — replaced naive bag-of-words keyword matching with BM25 ranking algorithm (term frequency saturation, inverse document frequency, document length normalization). Title boosting via token repetition. Configurable BM25_K1/BM25_B parameters. Custom tokenizer with stopword filtering and hyphen preservation. NOT RAG — searches pre-compiled wiki pages, not raw chunks. 252 tests.

## Phase 3.1 (complete, v0.9.0)
Hardening release — path traversal protection in `_validate_page_id()`, `kb_read_page`, `kb_create_page` (rejects `..` and absolute paths, verifies resolved path within WIKI_DIR). Citation regex fix (underscore support in page IDs). Slug collision tracking (`pages_skipped` in ingest result). JSON fence hardening (handles single-line `` ```json{...}``` ``). MCP error handling (all tools wrap external calls in try/except). `max_results` bounds [1, 100] in `kb_query`/`kb_search`. MCP instructions updated with Phase 2 tools. Anthropic SDK double-retry fix (`max_retries=0` on client). Redundant `.removesuffix(".md")` removed from linker/graph (already done by `extract_wikilinks`). 289 tests.

## Phase 3.2 (complete, v0.9.1)
Comprehensive audit and hardening — BM25 division-by-zero fix (avgdl=0 guard), source path traversal protection in `pair_page_with_sources()`, thread-safe LLM client singleton (double-check locking), `ValueError` on invalid tier, O(1) wiki log append (replaces O(n) read-modify-write), narrowed exception handling in `load_all_pages()` (specific types, not broad `Exception`), frontmatter-aware source collision detection in `_update_existing_page()`, consistent `_validate_page_id()` usage across all MCP tools, confidence level validation in `kb_create_page`, `yaml_escape` handles `\r` and `\0`, feedback/verdict 10k entry retention limits, duplicate "could" removed from semantic lint. Test coverage: 93 new tests (289→382) across 6 new test files — `test_llm.py` (27, LLM retry logic), `test_lint_verdicts.py` (12, verdict storage), `test_paths.py` (6, canonical paths), `test_mcp_browse_health.py` (15, browse/health tools), `test_mcp_core.py` (14, core tools), `test_mcp_quality_new.py` (12, quality tools). MCP tool test coverage 41%→95%.

## Phase 3.3 (complete, v0.9.2)
Audit fixes — 15 bug fixes, 31 new tests (382→413 net; 414 after rounding at time of writing). Test files: `test_ingest_fixes_v092.py` (8), `test_lint_query_fixes_v092.py` (12), `test_validation_fixes_v092.py` (11). Plan: `docs/superpowers/plans/2026-04-07-v092-audit-fixes.md`.

Ingest pipeline: fixed flawed regex in `_update_existing_page()` (replaced negative lookahead with `finditer` last-match approach), added logging to silent exception handler (specific types instead of bare `except`), surfaced `pages_skipped` in CLI and MCP output. Semantic lint: removed domain terms from `common_words` stoplist ("entity", "concept", etc.), fixed consistency group truncation (chunks instead of silent discard). Query engine: added context truncation logging, BM25 avgdl guard logging. MCP: case-insensitive page lookup now validates resolved path stays in WIKI_DIR, `logger.exception` → `logger.error` in health tools. Input validation: feedback store enforces length limits (question/notes 2000 chars, page ID 200 chars, max 50 cited pages, path traversal rejection), verdict severity validation (`error`/`warning`/`info`), refiner rejects content starting with `---`. Config: dev dependencies added to pyproject.toml.

## Phase 3.4 (complete, v0.9.3)
Feature completion — `kb_compile` MCP tool (22nd tool, calls `compile_wiki()` for full API-driven compilation), `kb lint --fix` implementation (auto-fixes dead links by replacing broken `[[wikilinks]]` with plain text, plumbed through runner and CLI), `MAX_SEARCH_RESULTS` config constant (replaces hardcoded 100 in `kb_query`/`kb_search`), manifest behavior verified with tests. 17 new tests (414→431).

## Phase 3.5 (complete, v0.9.4)
Tier 1-3 improvements — `build_backlinks()` now filters broken links (consistent with `build_graph()`), `analyze_coverage()` uses `parent.name` instead of fragile string containment, redundant `.removesuffix(".md")` removed from evolve, JSON fence stripping handles whitespace. Stub page detection in lint (`check_stub_pages()` — flags pages with <100 chars body, skips summaries) integrated into `run_all_checks()` and evolve recommendations. Content drift detection (`detect_source_drift()`) finds wiki pages stale due to raw source changes, new `kb_detect_drift` MCP tool (23rd tool). 21 new tests (431→452).

## Phase 3.6 (complete, v0.9.5)
Tier-1 audit hardening — extraction data type validation in ingest pipeline (`isinstance` guard for `entities_mentioned`/`concepts_mentioned`), `UnicodeDecodeError` handling in graph builder (`build_graph()` skips unreadable pages instead of crashing), empty title validation in `kb_create_page`, MCP instructions string updated with 3 missing tools (`kb_compile`, `kb_detect_drift`, `kb_save_source`), evolve stub check logs on failure instead of silent `pass`, `fix_dead_links()` writes audit trail to `wiki/log.md`. 13 new tests (452→465).

## Phase 3.7 (complete, v0.9.6)
Tier-2 audit hardening — query context skips whole pages instead of truncating mid-page (preserves markdown structure), atomic writes for feedback/verdict stores (temp file + rename), empty query validation in `kb_search`, entity/concept count limit per ingest (`MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50`), citation path traversal validation (rejects `..` and leading `/`), bare except logging in `kb_refine_page`, evolve surfaces low-trust pages from feedback (`flagged_pages` in report + recommendation). 18 new tests (465→483).

## Phase 3.8 (complete, v0.9.7)
Tier-3 fixes and observability — query search logs debug when falling back to raw terms (all stopwords), `kb_affected_pages` uses `debug` instead of `warning` for expected shared-sources failure, `LLMError` messages now distinguish error types (timeout, rate limit, connection, server error with status code). 7 new tests (483→490).

## Phase 3.9a (complete, v0.9.8)
Deep audit fixes and structured outputs — `kb_ingest` path traversal protection (validates resolved path stays within `PROJECT_ROOT`), `call_llm_json()` structured output via Claude tool_use (forced tool choice guarantees valid JSON, eliminates 13 lines of fence-stripping/JSON parsing), `build_extraction_schema()` + `_parse_field_spec()` for template→JSON Schema conversion (handles both simple and annotated field formats, `KNOWN_LIST_FIELDS` set for type inference), `_make_api_call()` shared retry helper (extracted from `call_llm`, used by both `call_llm` and `call_llm_json`), feedback trust score deduplication (`cited_pages` deduplicated before scoring to prevent inflated trust), atomic writes for review history (tempfile+rename pattern matching feedback/verdict stores). Simplify pass: `atomic_json_write()` utility in `kb.utils.io` (consolidated 3 identical atomic write implementations), `_resolve_model()` helper (deduplicated tier validation from `call_llm`/`call_llm_json`), removed dead 429 from `APIStatusError` retry codes (handled by `RateLimitError` catch), `load_template()` LRU-cached, precompiled regex in `_parse_field_spec()`, stale prompt instruction updated for tool_use. 29 new tests (490→518) in `test_v098_fixes.py`.

## Phase 3.9 (complete, v0.9.9)
Infrastructure for content growth and AI leverage — 8 features implemented, 32 new tests (518→550), 2 new MCP tools (23→25). Environment-configurable model tiers (`CLAUDE_SCAN_MODEL`, `CLAUDE_WRITE_MODEL`, `CLAUDE_ORCHESTRATE_MODEL` env vars override defaults in `config.py`). PageRank-blended search ranking (`final_score = bm25_score * (1 + PAGERANK_SEARCH_WEIGHT * normalized_pagerank)` — well-linked pages rank higher, `PAGERANK_SEARCH_WEIGHT=0.5` config). Duplicate detection in ingest (hash-based dedup in `ingest_source()` — checks compile manifest for existing sources with identical content hash, verifies other source still exists). Verdict trend dashboard (`kb_verdict_trends` MCP tool — weekly pass/fail/warning rates, quality trend direction, new `kb.lint.trends` module). Mermaid graph export (`kb_graph_viz` MCP tool — exports knowledge graph as Mermaid flowchart with auto-pruning to top N nodes by degree, subgraph grouping by page type, new `kb.graph.export` module). Retroactive inbound wikilink injection (`inject_wikilinks()` in `kb.compile.linker`). Content-length-aware ingest tiering (`SMALL_SOURCE_THRESHOLD=1000`). Cascade update detection on ingest (`affected_pages` return key).

### Post-review fixes (v0.9.9)
14 new tests (550→564). `inject_wikilinks` integrated into `ingest_source()` — automatically called for each newly created page (lazy import avoids circular dependency). `_format_ingest_result` shows "Duplicate content detected" with hash when `duplicate=True`. Surfaces `affected_pages` in `kb_ingest` output.

### DRY review fixes (v0.9.9, round 2)
3 new tests (564→567). Bugfix: `_update_existing_page` now accepts `verb: str = "Mentioned"` parameter — concept pages updated via a second source now correctly write `"Discussed in"`. `_process_item_batch` derives `subdir` from `_SUBDIR_MAP[page_type]` internally. `_update_index_batch` uses null guard on `_SUBDIR_MAP.get()`. Lazy imports restored for `build_backlinks`/`inject_wikilinks` (circular import risk).

### MCP output fixes (v0.9.9, round 3)
7 new tests (567→574). Two `_format_ingest_result` bugs fixed: (1) `affected_pages` flat `list[str]` was silently dropped by `isinstance(affected, dict)` guard — now handled with `elif isinstance(affected, list)`; (2) `wikilinks_injected` key was documented but never read by the formatter — now shown as "Wikilinks injected (N):" section.

## Phase 3.91 (complete, v0.9.10)
5-agent parallel code review fix list. 574 tests. Key fixes: `save_manifest` now uses `atomic_json_write`. `inject_wikilinks` frontmatter split uses regex (`_FRONTMATTER_RE`). `resolve_wikilinks`/`build_backlinks` wrap `read_text()` in `try/except (OSError, UnicodeDecodeError)`. `KNOWN_LIST_FIELDS` extended with `key_arguments`, `quotes`, `themes`, `open_questions`. Mermaid `_safe_node_id` tracks seen IDs with suffix deduplication. `run_all_checks` with `fix=True` removes fixed issues from report. `kb_ingest` wrapped in `try/except`. `kb_create_page` uses `_validate_page_id(check_exists=False)`. URL in `kb_ingest_content`/`kb_save_source` wrapped in `yaml_escape()`. `VERDICTS_PATH` and LLM retry constants moved to `config.py`. `detect_source_drift` bare `except` narrowed. `extract_raw_refs` extended to `.csv`/`.png`/`.jpg`/`.jpeg`/`.svg`/`.gif`.
