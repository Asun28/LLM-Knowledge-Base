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

Post-release audit fixes for Phase 4 v0.10.0 — all HIGH (23) + MEDIUM (~30) + LOW (~30) items.
Plus Phase 4.1 sweep: 16 LOW/NIT backlog items applied directly (no test changes).

### Phase 4.1 — easy backlog sweep (2026-04-14)
- `src/kb/capture.py` `_check_rate_limit` — `retry_after = max(1, ...)` so frozen-clock test fixtures can't yield ≤0 retry hints
- `src/kb/capture.py` `_validate_input` — ASCII fast-path skips full UTF-8 encode() for the common case
- `src/kb/capture.py` `_CAPTURE_SECRET_PATTERNS` — GCP OAuth `ya29.` pattern tightened to require 20+ char suffix (prevents false positives like `ya29.Overview`)
- `src/kb/capture.py` `_normalize_for_scan` — removed dead `except (ValueError, UnicodeDecodeError)` around `urllib.parse.unquote()` (unreachable — unquote uses `errors='replace'`)
- `src/kb/capture.py` `_path_within_captures` — now also catches `OSError` (ELOOP/EACCES on resolve) instead of propagating as unhandled 500
- `src/kb/capture.py` `_write_item_files` — early return on empty items skips mkdir + scandir
- `src/kb/capture.py` `_build_slug` — added explanatory comment on the collision loop bound
- `src/kb/capture.py` `_write_item_files` — added O(N²) comment on the `alongside_for` computation
- `src/kb/capture.py` module-level symlink guard — `.resolve()` calls wrapped in try/except `OSError` → `RuntimeError` for clear mount-failure diagnostics
- `src/kb/utils/text.py` `yaml_sanitize` — hoisted `_CTRL_CHAR_RE` to module scope (no recompile per call)
- `src/kb/graph/builder.py` `page_id` — uses `Path.as_posix()` instead of `str().replace("\\", "/")` for canonical cross-platform serialization
- `src/kb/lint/checks.py` `_INDEX_FILES` — dropped `"_categories.md"` (file never written; dead lookup removed)
- `src/kb/utils/hashing.py` `content_hash` — docstring now documents 128-bit prefix + collision bound + non-security use
- `src/kb/query/bm25.py` `tokenize` — docstring now mentions `STOPWORDS` filter so readers understand why `"what is rag"` → `["rag"]`
- `src/kb/evolve/analyzer.py` `suggest_new_pages` — skips empty wikilink targets (prevents ghost "Create  — referenced by …" suggestions from `[[   ]]` artifacts)

### Added
- **`kb_capture` MCP tool** — atomize up to 50KB of unstructured text (chat logs, scratch notes, LLM session transcripts) into discrete `raw/captures/<slug>.md` files via scan-tier LLM. Each item gets typed `kind` (decision / discovery / correction / gotcha), verbatim body, and structured frontmatter (title, confidence, captured_at, captured_from, captured_alongside, source). Returns file paths for subsequent `kb_ingest`. New `kb.capture` module + `templates/capture.yaml` + 5 new MCP wrapper tests + ~130 library tests.
- **Secret scanner with reject-at-boundary** — `kb_capture` content scanned for AWS / OpenAI / Anthropic / GitHub / Slack / GCP / Stripe / HuggingFace / Twilio / npm / JWT / DB connection strings / private key blocks BEFORE any LLM call; matches reject the entire batch with precise pattern label and line number. Encoded-secret normalization pass catches base64-wrapped and URL-encoded patterns (3+ adjacent triplets).
- **Per-process rate limit** — `kb_capture` enforces a 60-call-per-hour sliding-window cap under `threading.Lock` for FastMCP concurrent-request safety. Configurable via `CAPTURE_MAX_CALLS_PER_HOUR`.
- **`templates/capture.yaml`** — new ingest template for `raw/captures/*.md` with field names matching existing pipeline (`core_argument`, `key_claims`, `entities_mentioned`, `concepts_mentioned`).
- **`yaml_escape` strips Unicode bidi override marks** (`\u202a-\u202e`, `\u2066-\u2069`) — defends LLM-supplied frontmatter values against audit-log confusion attacks where U+202E renders text backward in terminals.
- **`pipeline.py` strips frontmatter for capture sources** — when `kb_ingest` processes a `raw/captures/*.md` file, leading YAML frontmatter is stripped before write-tier extraction. Gated on `source_type == "capture"` so other sources (Obsidian Web Clipper, arxiv) preserve their frontmatter for the LLM.
- `research/gbrain-analysis.md` — deep analysis of garrytan/gbrain patterns applicable to llm-wiki-flywheel roadmap
- `src/kb/utils/hashing.py` `hash_bytes()` — hash already-loaded bytes without re-reading the file; fixes TOCTOU inconsistency in ingest pipeline
- `src/kb/utils/io.py` `file_lock()` — cross-process exclusive lock via PID-stamped lock file with stale-lock detection; replaces `threading.Lock` in feedback store and verdicts
- `src/kb/config.py` `BM25_SEARCH_LIMIT_MULTIPLIER` — decouples BM25 candidate count from vector search multiplier in hybrid search
- `tests/test_phase4_audit_security.py` — 7 tests covering null-byte validation, content size bounds, and prompt injection
- `tests/test_phase4_audit_observability.py` — 4 tests covering retry logging, PageRank convergence warning, sqlite_vec load warning, and compile exception traceback
- `tests/test_phase4_audit_query.py` — 5 tests covering tier-1 budget enforcement, raw fallback truncation, and BM25 limit decoupling
- `tests/test_phase4_audit_compile.py` — 4 tests covering manifest pruning, source_id case normalisation, bare-slug resolution, and word normalisation
- `tests/test_phase4_audit_ingest.py` — 8 tests covering TOCTOU hash, sources-mapping merge, template key guards, and markdown stripping in contradiction detection
- `tests/test_phase4_audit_concurrency.py` — 4 tests covering cross-process file locking for feedback store and verdicts

### Changed
- `CLAUDE.md` Phase 4 roadmap expanded from 5 → 8 features: added hybrid search with RRF fusion (replaces LLM keyword expansion), 4-layer search dedup pipeline, evidence trail sections in wiki pages, stale truth flagging at query time — all inspired by garrytan/gbrain
- `CLAUDE.md` Phase 5 roadmap: removed BM25 + LLM reranking (subsumed by Phase 4 RRF), upgraded chunk-level indexing to use Savitzky-Golay semantic chunking, added cross-reference auto-linking during ingest
- `src/kb/feedback/store.py` `_feedback_lock` — switched from `threading.Lock` to `file_lock` for cross-process safety
- `src/kb/lint/verdicts.py` `add_verdict` — switched from `threading.Lock` to `file_lock` for cross-process safety

### Fixed

#### Security
- `src/kb/mcp/app.py` `_validate_page_id` — null bytes (`\x00`) now explicitly rejected before path resolution
- `src/kb/mcp/quality.py` `kb_refine_page` / `kb_create_page` — added `MAX_INGEST_CONTENT_CHARS` size bound on submitted content
- `src/kb/query/engine.py` `query_wiki` — synthesis prompt now uses `effective_question` (not raw `question`) with newlines collapsed to prevent prompt injection

#### Observability
- `src/kb/utils/llm.py` `_make_api_call` — final retry attempt now logs "giving up after N attempts" instead of the misleading "retrying in X.Xs"
- `src/kb/graph/builder.py` `graph_stats` — `PowerIterationFailedConvergence` now logs a warning with node count before returning empty results
- `src/kb/query/embeddings.py` `VectorIndex.query` — `sqlite_vec` extension load failure now logs a warning instead of silently returning empty results
- `src/kb/compile/compiler.py` `compile_wiki` — bare `except Exception` now calls `logger.exception()` to preserve full traceback in compile failure logs

#### Query correctness
- `src/kb/query/engine.py` `_build_query_context` — `CONTEXT_TIER1_BUDGET` now enforced; tier-1 loop tracks `tier1_used` separately to prevent summary pages consuming the entire context budget
- `src/kb/query/engine.py` `query_wiki` — raw-source fallback now truncates the first oversized section instead of producing no fallback context when the section exceeds remaining budget
- `src/kb/query/hybrid.py` `hybrid_search` — BM25 candidate count now uses `BM25_SEARCH_LIMIT_MULTIPLIER` (default 1×) instead of `VECTOR_SEARCH_LIMIT_MULTIPLIER` (2×), decoupling the two signals

#### Compile / graph
- `src/kb/compile/compiler.py` `compile_wiki` — manifest pruning now checks `Path.exists()` per key instead of comparing against `scan_raw_sources()` results; prevents phantom re-ingest when a source directory is temporarily unreadable
- `src/kb/compile/linker.py` `inject_wikilinks` — `source_id` now lowercased to match the lowercased `existing_ids` set; fixes silent lookup mismatches in broken-link reporting
- `src/kb/graph/builder.py` `build_graph` — bare-slug wikilinks (e.g., `[[rag]]`) now resolved by trying each wiki subdir prefix; fixes disconnected graph edges and corrupted PageRank scores
- `src/kb/evolve/analyzer.py` `find_connection_opportunities` — word normalisation now uses `re.sub(r"[^\w]", "", w)` to strip all non-word chars including `*`, `#`, `>`, `` ` ``, eliminating spurious shared-term matches from Markdown formatting tokens

#### Ingest data integrity
- `src/kb/ingest/pipeline.py` `ingest_source` — `source_hash` now derived from already-read `raw_bytes` via `hash_bytes()` instead of re-opening the file; eliminates TOCTOU inconsistency between content and hash
- `src/kb/ingest/pipeline.py` `_update_sources_mapping` — re-ingest now merges new page IDs into the existing `_sources.md` entry instead of returning early; previously new pages from re-ingest were silently dropped from the source mapping
- `src/kb/ingest/extractors.py` `build_extraction_prompt` — `template["name"]` and `template["description"]` replaced with `.get()` calls with fallbacks; prevents bare `KeyError` from user-authored templates missing optional keys
- `src/kb/ingest/contradiction.py` `detect_contradictions` — markdown structure (wikilinks, section headers) now stripped before tokenisation; prevents Evidence Trail boilerplate from inflating false overlap matches

#### Concurrency
- `src/kb/utils/io.py` `file_lock` — Windows `PermissionError` from `os.open(O_CREAT|O_EXCL)` now handled identically to `FileExistsError`; fixes concurrent thread contention on Windows

- **Phase 4 MEDIUM audit (~30 items)**: `load_all_pages` datetime→date normalisation; slugify version-number collision fix; `fd_transferred` flag prevents double-close in atomic writes; `extract_wikilinks` filters embedded newlines; `wiki_log` sanitises tabs; `FRONTMATTER_RE` consolidated to `kb.utils.markdown`; `STOPWORDS` consolidated to `kb.utils.text`; `VALID_VERDICT_TYPES` consolidated to `kb.lint.verdicts`; graph `out_degrees` precomputed dict (O(n) vs per-node `graph.degree`); graph export deterministic edge ordering; query citation path traversal guard; `_build_query_context` skipped-count fix; query engine removes inner config import; `_should_rewrite` checks deictic words before word count; rewriter length explosion guard; `VectorIndex` cached per-path via `get_vector_index()`; compiler `content_hash` isolated try/except; compiler `save_manifest` guarded; compiler skips `~`/`.` template stems; evolve `MAX_CONNECTION_PAIRS` cap; evolve `generate_evolution_report` single page-load; ingest contradiction appends to `WIKI_CONTRADICTIONS`; ingest `_build_summary_content` only on new pages; ingest references whitespace-line regex; ingest `_update_existing_page` early-return on missing frontmatter; ingest `_process_item_batch` raises on unknown type; ingest O(n) slug-lookup dicts; lint `check_orphan_pages` scans index/sources/categories/log; lint `check_source_coverage` uses rglob; lint `_group_by_term_overlap` bails at 500 pages; lint `_render_sources` budget fix; lint `_parse_timestamp` accepts date-only strings; MCP question/context length cap; MCP `kb_ingest` normcase path check; MCP atomic exclusive create; MCP `kb_list_pages` page_type validation; MCP `kb_graph_viz` treats max_nodes=0 as default; MCP `kb_detect_drift` None-safe join; MCP lint-verdict issues cap; MCP `kb_query_feedback` question length cap; MCP `kb_lint_consistency` page-ID cap.
- **Phase 4 LOW audit (~30 items)**: Consolidated `FRONTMATTER_RE`, `STOPWORDS`, `VALID_VERDICT_TYPES` as single sources of truth; BM25 avgdl branch demoted to debug; `graph/__init__.__all__` pruned; hybrid BM25 asymmetry comment; dedup Jaccard strips markup; type-diversity docstring; rewriter deictic word pattern; evidence CRLF-safe regex + `format_evidence_entry` helper; contradiction truncation log; contradiction symmetric-negation docstring; feedback eviction-policy comment; refiner `re.DOTALL` confirmed; refiner `re.MULTILINE` anchor; CLI error truncation via `_truncate(str(e), limit=500)` on all 5 command handlers.

### Changed
- `kb.utils.markdown.FRONTMATTER_RE` exported as public constant; `kb.graph.builder` and `kb.compile.linker` import it from there.
- `kb.utils.text.STOPWORDS` is the single source of truth; `kb.query.bm25` and `kb.ingest.contradiction` import from there.
- `kb.lint.verdicts.VALID_VERDICT_TYPES` is the single source of truth for verdict type names.
- `kb.query.embeddings.get_vector_index(path)` provides a singleton cache for `VectorIndex` instances.
- `kb.config` gains `WIKI_CONTRADICTIONS` path constant and `MAX_QUESTION_LEN = 2000`; removes unused `EMBEDDING_DIM`.

### Stats
- 1309 tests, 26 MCP tools, 19 modules

---

## [0.10.0] - 2026-04-12

Phase 4 — 8 features: hybrid search, dedup pipeline, evidence trails, stale flagging, layered context, raw fallback, contradiction detection, query rewriting.

### Added
- `src/kb/query/hybrid.py` — hybrid search: Reciprocal Rank Fusion of BM25 + vector results; `rrf_fusion()` and `hybrid_search()` with optional multi-query expansion
- `src/kb/query/dedup.py` — 4-layer search dedup pipeline: by source (highest score per page), text similarity (Jaccard >0.85), type diversity (60% cap), per-page cap (max 2)
- `src/kb/query/embeddings.py` — model2vec embedding wrapper (potion-base-8M, 256-dim, local) + sqlite-vec vector index (`VectorIndex` class)
- `src/kb/query/rewriter.py` — multi-turn query rewriting: scan-tier LLM expands pronouns/references in follow-up questions; heuristic skip for standalone queries
- `src/kb/ingest/evidence.py` — evidence trail sections: append-only `## Evidence Trail` provenance in wiki pages; `build_evidence_entry()` and `append_evidence_trail()`
- `src/kb/ingest/contradiction.py` — auto-contradiction detection on ingest: keyword overlap heuristic flags conflicts between new claims and existing wiki content
- `search_raw_sources()` in `kb.query.engine` — BM25 search over `raw/` source files for verbatim context fallback when wiki context is thin
- `_flag_stale_results()` in `kb.query.engine` — stale truth flagging at query time: compares page `updated` date vs source file mtime; adds `[STALE]` label in MCP output
- `_build_query_context()` refactored for tiered loading: summaries loaded first (20K chars), then full pages (60K chars), replacing naive 80K truncation
- `conversation_context` parameter on `query_wiki()` and `kb_query` MCP tool for multi-turn rewriting
- Evidence trail wired into ingest pipeline: `_write_wiki_page` and `_update_existing_page` automatically append provenance entries
- Auto-contradiction detection wired into `ingest_source()`: runs post-wikilink-injection, returns `contradictions` key in result dict
- `search_pages()` now uses `hybrid_search()` with RRF fusion + `dedup_results()` pipeline

### Changed
- `src/kb/config.py` — added 12 Phase 4 constants: `RRF_K`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `VECTOR_INDEX_PATH_SUFFIX`, dedup thresholds, context tier budgets, contradiction/rewriter limits

### Stats
- 1079 tests, 25 MCP tools, 18 modules

---

## [0.9.16] - 2026-04-12

Phase 3.97 — 62 fixes from 6-domain code review of v0.9.15.

### Fixed

#### CRITICAL
- Non-atomic writes in `fix_dead_links`, `kb_create_page`, `inject_wikilinks` replaced with `atomic_text_write`
- MCP exception guard on `kb_query` non-API path (search failures no longer crash sessions)
- `kb_save_lint_verdict` now catches `OSError` alongside `ValueError`
- Confirmed `refine_page` atomic write was already fixed in v0.9.15

#### HIGH
- `slugify` now maps C++→cpp, C#→csharp, .NET→dotnet to prevent cross-ingest entity merging
- `load_all_pages` coerces integer titles to strings (prevents `AttributeError` in BM25 search)
- `kb_query` API mode now forwards `max_results` parameter
- `kb_ingest_content`/`kb_save_source` raw file writes are now atomic
- `fix_dead_links` masks code blocks before modifying wikilinks
- `_is_valid_date` rejects empty strings and non-ISO date values
- `refine_page` catches `OSError`/`UnicodeDecodeError` on file read
- `load_review_history` catches `OSError`/`UnicodeDecodeError`, validates list shape
- `check_source_coverage` guards against `ValueError` from symlinks
- `load_feedback` validates `entries` is list and `page_scores` is dict (not null)
- `add_feedback_entry` initializes missing keys with defaults before arithmetic
- `kb_reliability_map` uses `.get()` for all score keys
- `kb_create_page` rejects nested page_id with more than one slash
- `kb_read_page` catches `UnicodeDecodeError`
- Feedback lock adds sleep after stale lock eviction

#### MEDIUM
- `atomic_text_write`/`atomic_json_write` write LF line endings on Windows (fixes cross-platform hash mismatches)
- `yaml_escape` strips Unicode NEL (`\x85`)
- `_update_index_batch` uses wikilink-boundary match instead of substring
- Title sanitization in `_update_index_batch`, `inject_wikilinks`, `_build_item_content`, `_build_summary_content`
- `build_extraction_schema` rejects `extract: None` templates
- `VALID_SOURCE_TYPES` includes comparison/synthesis
- `SUPPORTED_SOURCE_EXTENSIONS` shared constant replaces duplicate extension lists
- Binary PDF files get clear error instead of silent `UnicodeDecodeError`
- `detect_source_type` accepts custom `raw_dir` parameter
- PageRank returns empty for edge-free graphs instead of uniform 1.0
- `_compute_pagerank_scores` catches `OSError`
- `export_mermaid` uses `graph.subgraph()` for efficient edge iteration
- `_sanitize_label` falls back to slug on empty result
- `extract_citations` overrides type based on path prefix (raw/ paths → "raw")
- Citation regex hoisted to module level
- `compile` CLI exits code 1 on errors
- Verdict trends checks explicit verdict values, not dict membership
- `build_consistency_context` shows missing pages, filters single-page chunks
- Evolve frontmatter strip regex handles CRLF
- `generate_evolution_report` catches all exceptions in stub check
- `kb_create_page` requires source_refs to start with "raw/"
- `kb_query` coerces `None` trust to 0.5
- `kb_query_feedback` sanitizes question/notes control chars
- `_validate_page_id` rejects empty strings
- Various control character sanitization in MCP tools

#### LOW
- `WIKILINK_PATTERN` excludes `![[embed]]` syntax
- `_RAW_REF_PATTERN` case-insensitive, excludes hyphen before `raw/`
- `normalize_sources` filters empty strings and warns on non-string items
- `RawSource.content_hash` default standardized to `None`
- `RESEARCH_DIR` annotated as reserved
- Config constants for `UNDER_COVERED_TYPE_THRESHOLD`, `STUB_MIN_CONTENT_CHARS`
- `kb_list_sources` excludes `.gitkeep` files
- `kb_save_lint_verdict` uses `MAX_NOTES_LEN` constant
- Template cache clear helper added
- `ingest_source` uses `content_hash()` utility
- CLI source type list derived from `SOURCE_TYPE_DIRS`
- `graph_stats` narrows betweenness_centrality exception, adds `ValueError` to PageRank
- BM25 tokenize regex dead branch removed
- `query_wiki` docstring documents citation dict structure
- `get_coverage_gaps` deduplicates repeated questions

### Stats
1033 tests, 25 MCP tools, 12 modules.

---

## [0.9.15] — 2026-04-11

### Fixed
- **CRITICAL**: Non-atomic wiki page writes — crash mid-write could leave truncated files (ingest/pipeline, compile/linker, review/refiner)
- **CRITICAL**: TOCTOU race in `_update_existing_page` — double file read replaced with in-memory parse
- **CRITICAL**: Frontmatter guard regex allowed empty `---\n---` blocks through, causing double-frontmatter corruption
- **CRITICAL**: `kb_query` MCP tool missing empty-question guard
- `yaml_escape` now strips ASCII control characters (0x01-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F) that cause PyYAML ScannerError
- `normalize_sources` returns empty list for dict/int/float types instead of silently returning dict keys or raising TypeError
- `WIKILINK_PATTERN` rejects triple brackets `[[[...]]]` and caps match length at 200 chars
- `wiki_log` sanitizes newline/carriage return characters in operation and message fields
- `_page_id` in `utils/pages.py` now lowercases, consistent with `graph/builder.py`
- `WIKI_SUBDIRS` derived from `config.WIKI_SUBDIR_TO_TYPE` instead of hardcoded in 3 modules
- `load_all_pages` converts `null` dates to empty string instead of literal `"None"`
- `content_hash` uses streaming reads instead of loading entire file into memory
- `atomic_json_write` rejects `NaN`/`Infinity` values (`allow_nan=False`)
- `compile_wiki` forwards `wiki_dir` parameter to `ingest_source`
- Manifest double-write race fixed — compile loop reloads manifest after each ingest
- Partial ingest failure records hash with `failed:` prefix to prevent infinite retry
- `inject_wikilinks` guards against empty titles, fixes closure bug, skips blocked matches correctly
- Source ref injection targets `source:` block specifically, not any YAML list item
- Context block dedup checks for `## Context` header, not full block substring
- `extract_citations` dead code removed, `./` path traversal blocked
- Graph builder: self-loop guard, deterministic betweenness centrality (seed=0), frontmatter stripped before wikilink extraction
- Backlinks dedup changed from O(n²) list scan to O(1) set operations
- Code masking extended to markdown links/images, UUID-prefix placeholders prevent collision
- Lint: `fix_dead_links` count corrected, `resolve_wikilinks` deduped, threading locks added for verdicts/history
- Star-topology grouping uses `nx.connected_components` for complete coverage
- `check_staleness` handles unexpected `updated` types (int, etc.)
- Consistency groups auto-capped at `MAX_CONSISTENCY_GROUP_SIZE`
- Stale lock recovery retries acquisition instead of falling through unprotected
- Feedback lock creates `.data/` directory if missing
- Cross-link opportunity ranking uses uncapped term count
- MCP: path boundary tightened to `RAW_DIR`, filename/content length caps, page_id validation for cited_pages
- Review checklist verdict vocabulary aligned with `add_verdict()` accepted values
- CLI shows duplicate detection, removes invalid `comparison`/`synthesis` from source type choices
- `query_wiki` API documentation corrected in CLAUDE.md

### Changed
- `validate_frontmatter` checks date field types and source list item types
- `conftest.py` `create_wiki_page` fixture supports separate `created` parameter
- `extract_raw_refs` uses word-boundary anchor to avoid URL false positives
- `detect_source_type` gives clear error message for `raw/assets/` files
- Bare `except Exception` narrowed to specific exception tuples in lint/semantic modules

### Stats
952 tests, 25 MCP tools, 12 modules.

---

## [0.9.14] - 2026-04-09 (Phase 3.95)

38-item backlog fix pass across 13 source files. No new modules. All fixes have tests in `tests/test_v0914_phase395.py`.

### Fixed
- `utils/io.py` `atomic_json_write` — close fd on serialization failure (fd leak)
- `utils/paths.py` `make_source_ref` — always use literal `"raw/"` prefix instead of resolved dir name
- `utils/llm.py` `_make_api_call` — skip sleep after final failed retry
- `utils/text.py` `slugify` — add `re.ASCII` flag to strip non-ASCII chars
- `utils/wiki_log.py` `append_wiki_log` — wrap write+stat in `try/except OSError`, log warning instead of raising
- `models/frontmatter.py` `validate_frontmatter` — flag `source: null` and non-list/str source fields
- `models/page.py` `WikiPage` — `content_hash` defaults to `None` instead of `""`
- `query/engine.py` `search_pages` — no mutation of input page dicts (use spread-copy for score)
- `query/engine.py` `_build_query_context` — returns dict with `context` and `context_pages` keys; small-max_chars guard
- `query/engine.py` `query_wiki` — includes `context_pages` in return dict; fixed missing key in no-match early return
- `query/bm25.py` `tokenize` — documented version-string fragmentation behavior
- `ingest/pipeline.py` `_update_existing_page` — CRLF-safe frontmatter regex (`\r?\n`)
- `ingest/pipeline.py` `_build_summary_content` — handle dict authors via `a.get("name")`, drop non-str/non-dict with warning
- `ingest/pipeline.py` `ingest_source` — thread `wiki_dir` through all helpers; `_update_index_batch` and `_update_sources_mapping` use `atomic_text_write`
- `utils/io.py` — add `atomic_text_write` helper (temp file + rename for text files)
- `ingest/extractors.py` `_parse_field_spec` — warn on non-identifier field names
- `compile/compiler.py` `compile_wiki` — reload manifest after `find_changed_sources` to preserve template hashes
- `compile/linker.py` `inject_wikilinks` — mask code blocks before wikilink injection; unmask before write
- `lint/checks.py` `check_staleness` — flag pages with `None`/missing `updated` date
- `lint/runner.py` `run_all_checks` — use `f.get("source", f.get("page"))` for dead-link key consistency
- `lint/checks.py` `check_source_coverage` — use `make_source_ref` instead of hardcoded `raw/` prefix
- `lint/checks.py` `check_stub_pages` — narrow `except Exception` to specific exception types
- `lint/semantic.py` `_group_by_wikilinks` — `seen.update(group)` so all group members marked seen (prevents overlapping groups)
- `lint/semantic.py` `_group_by_term_overlap` — strip-before-filter using walrus operator
- `lint/trends.py` `compute_verdict_trends` — require minimum 3 verdicts in latest period for trend classification
- `lint/verdicts.py` `add_verdict` — truncate long notes instead of raising `ValueError`
- `graph/builder.py` `page_id` — normalize node IDs to lowercase
- `evolve/analyzer.py` `find_connection_opportunities` — strip-before-filter using walrus operator
- `evolve/analyzer.py` `generate_evolution_report` — narrow `except Exception` to specific types
- `mcp/core.py` `kb_ingest_content` — return error instead of overwriting existing source file
- `mcp/core.py` `kb_ingest` — truncate oversized content before building extraction prompt
- `feedback/store.py` `add_feedback_entry` — UNC path guard via `os.path.isabs`; file locking via `_feedback_lock`
- `feedback/store.py` — move constants to `config.py`
- `config.py` — add feedback store constants (`MAX_QUESTION_LEN`, `MAX_NOTES_LEN`, `MAX_PAGE_ID_LEN`, `MAX_CITED_PAGES`)
- `review/refiner.py` `refine_page` — write page file before appending history; OSError returns error dict
- `mcp/quality.py` `kb_create_page` — derive `type_map` from config instead of hardcoding

### Stats
692 tests, 25 MCP tools, 12 modules.

---

## [0.9.13] - 2026-04-09 (Phase 3.94)

54-item backlog fix pass covering BM25, query engine, citations, lint, ingest, compile, MCP, graph, evolve, feedback, refiner, and utils. Ruff clean. Plus cross-cutting rename `raw_content` → `content_lower` in `load_all_pages` and all callers.

### Fixed
- `query/bm25.py` `BM25Index.score`: deduplicate query tokens via `dict.fromkeys()` — duplicate terms no longer inflate BM25 scores against standard behavior
- `query/engine.py` `search_pages`: remove dead stopword-fallback block (BM25 index has no stopword entries; fallback never matched); add `max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))` upper-bound clamp at library level
- `query/engine.py` `_build_query_context`: emit `logger.warning` when the top-ranked page (`i == 0`) is excluded because it exceeds `max_chars` — previously silently skipped with only a DEBUG log
- `query/citations.py` `extract_citations`: add pre-pass normalizing `[[path]]` → `path` inside `[source: ...]` brackets — wikilink-wrapped citation paths were silently dropped
- `lint/runner.py` `run_all_checks`: fix post-fix dead-link filter — field name mismatch `"source"` vs `"page"` meant the filter was a no-op; fixed links now correctly removed from the report; add `logger.warning` when `get_verdict_summary()` raises — previously silent
- `lint/checks.py` `check_staleness`: add `TypeError` to except clause and coerce `datetime.datetime` → `datetime.date` — pages with ISO-datetime `updated` fields aborted the entire staleness check
- `lint/checks.py` `check_orphan_pages` / `check_cycles`: accept optional pre-built graph parameter; `run_all_checks` builds graph once and passes it to both — eliminates double full-graph build per lint run
- `lint/verdicts.py` `add_verdict`: add path-traversal guard (reject `..` and leading `/`/`\`); cap `notes` at `MAX_NOTES_LEN` consistent with feedback store
- `ingest/pipeline.py` `_update_existing_page`: scope source-entry regex to frontmatter section only (split on closing `---`) — regex previously matched any indented quoted list item in the page body
- `ingest/pipeline.py` `_process_item_batch`: add `isinstance(item, str)` guard — non-string items (`None`, int, nested dict) now log a warning and skip instead of raising `AttributeError`
- `ingest/pipeline.py` `ingest_source`: add fallback slug `source_path.stem` when `slugify(title)` returns empty string — punctuation-only titles no longer create hidden dotfile pages
- `ingest/pipeline.py` `_update_sources_mapping`: change plain substring match to backtick-wrapped format check (`` f"`{source_ref}`" in content ``) — `raw/articles/a.md` no longer falsely matches `raw/articles/abc.md`
- `ingest/pipeline.py` `_build_summary_content`: filter `authors` list with `isinstance` guard before `join` — `None` elements no longer raise `TypeError`; same guard applied to `slugify()` calls over `entities_mentioned`/`concepts_mentioned`
- `ingest/pipeline.py` `_write_wiki_page`: rename local variable `frontmatter` → `fm_text` to stop shadowing the `import frontmatter` module
- `ingest/pipeline.py` `_extract_entity_context`: use `is not None` check for `key_claims` — an explicitly empty `[]` primary field no longer triggers the fallback to `key_points`
- `compile/linker.py` `inject_wikilinks`: lowercase `target_page_id` at function entry — self-skip check and injected wikilink now consistently lowercased; log warning when nested-wikilink guard fires and blocks injection
- `compile/linker.py` `resolve_wikilinks`: lowercase `existing_ids` — case-sensitive filesystems no longer produce false broken-link reports for mixed-case page IDs
- `compile/compiler.py` `compile_wiki`: capture `content_hash(source)` before calling `ingest_source` — externally modified files during ingest no longer cause manifest drift
- `compile/compiler.py` `compile_wiki`: reload manifest after `find_changed_sources` returns — template hashes are no longer overwritten by per-source `save_manifest` calls in the loop
- `compile/compiler.py` `scan_raw_sources`: emit `logger.warning` for subdirs under `raw/` not in `SOURCE_TYPE_DIRS` (excluding `assets`) — new source types added to config but not here are now visible
- `compile/compiler.py` `_canonical_rel_path`: add `logger.warning` when fallback (absolute path as manifest key) fires
- `mcp/core.py` `kb_ingest_content`: wrap `file_path.write_text()` and `ingest_source()` in `try/except`; on exception, delete the orphaned raw file before returning `"Error: ..."`
- `mcp/quality.py` `kb_create_page`: wrap `page_path.write_text()` and `append_wiki_log` in `try/except OSError` — unhandled OS errors no longer escape to MCP client
- `mcp/quality.py` `kb_query_feedback`: catch `OSError` after existing `ValueError` handler — disk-full/permissions errors now return `"Error: ..."` instead of propagating
- `mcp/quality.py` `kb_lint_consistency`: use `check_exists=True` when explicit page IDs are supplied — non-existent pages now return a clear error instead of silent empty output
- `mcp/health.py` `kb_graph_viz`: clamp `max_nodes = max(0, min(max_nodes, 500))` at tool boundary — unbounded values no longer risk memory exhaustion
- `mcp/health.py` `kb_lint` / `kb_evolve`: promote feedback-data load failure from `DEBUG` to `logger.warning` — corrupt feedback store is no longer invisible at default log level
- `mcp/app.py` `_format_ingest_result`: use `.get()` for `pages_created` and `pages_updated` — partial/error-state result dicts no longer raise `KeyError`
- `mcp/browse.py` `kb_list_sources`: wrap per-file `f.stat()` in `try/except OSError` — a broken symlink no longer aborts the entire directory listing
- `mcp/core.py` `kb_ingest`: add soft size warning when source exceeds `QUERY_CONTEXT_MAX_CHARS` — multi-megabyte sources now log a warning before extraction
- `utils/paths.py` `make_source_ref`: raise `ValueError` for paths outside `raw/` instead of returning a fabricated path — silent collision with legitimate `raw/` files prevented
- `utils/llm.py` `call_llm`: iterate `response.content` to find the first `type == "text"` block instead of assuming `[0]` is text — `thinking` blocks first no longer cause `AttributeError`
- `utils/llm.py` `_make_api_call`: fix retry log denominator from `MAX_RETRIES` to `MAX_RETRIES + 1` — no longer logs "attempt 4/3" on final attempt
- `utils/wiki_log.py` `append_wiki_log`: sanitize `|` chars in `operation` and `message` before writing — pipe characters no longer produce unparseable extra columns in the log
- `utils/pages.py` `normalize_sources`: filter non-string elements — malformed YAML `source:` fields with nested items no longer cause downstream `AttributeError`
- `utils/hashing.py` `content_hash`: fix docstring — "32-char hex digest" corrected to "first 32 hex chars (128-bit prefix of SHA-256)"
- `ingest/extractors.py`: add `_build_schema_cached(source_type: str)` LRU-cached wrapper around `load_template` + `build_extraction_schema` — schema is no longer rebuilt on every extraction call
- `graph/builder.py` `graph_stats`: wrap `betweenness_centrality` in `try/except Exception` with `logger.warning` — unexpected failures no longer propagate to caller
- `graph/builder.py` `graph_stats`: rename `"orphans"` key → `"no_inbound"` — aligns with lint module's definition (zero backlinks regardless of out-degree)
- `graph/export.py` `_sanitize_label`: strip `(` and `)` from Mermaid node labels — parentheses caused parse errors in some renderer versions
- `graph/export.py` `export_mermaid`: quote subgraph names (`subgraph "{page_type}"`) — future page types with spaces produce valid Mermaid syntax
- `evolve/analyzer.py` `generate_evolution_report`: promote `check_stub_pages` / `get_flagged_pages` exception logging from `DEBUG` to `logger.warning` — genuine bugs no longer silently omit report sections
- `evolve/analyzer.py` `find_connection_opportunities`: replace O(V×T) re-scan with `pair_shared_terms` accumulator in outer loop — eliminates redundant full `term_index` iteration per qualifying pair
- `feedback/store.py` `load_feedback`: validate JSON shape after load (`isinstance(data, dict)` + required keys check) — wrong-shaped files now return `_default_feedback()` instead of raising `KeyError`
- `review/refiner.py` `refine_page`: tighten `startswith("---")` guard to `startswith("---\n") or == "---"` — valid markdown opening with a horizontal rule (`---\n`) no longer falsely rejected
- `lint/semantic.py` `_group_by_wikilinks`: remove dead `existing_neighbors` filter — `build_graph` only creates edges to existing nodes; filter never removed anything
- `models/frontmatter.py` `load_page`: remove dead function with zero callsites — `lint/checks.py` uses `frontmatter.load()` directly

### Changed
- `utils/pages.py` `load_all_pages`: rename field `raw_content` → `content_lower` — name now accurately reflects that the field is pre-lowercased for BM25, not verbatim content; all callers updated (`query/`, `lint/`, `compile/`, `evolve/`)
- `mcp/browse.py`: simplified `except (OSError, PermissionError)` → `except OSError` in `kb_read_page` and `kb_list_sources` (`PermissionError` is a subclass of `OSError`)
- `compile/compiler.py` `load_manifest`: returns `{}` on `json.JSONDecodeError` or `UnicodeDecodeError` instead of propagating — corrupt `.data/hashes.json` no longer crashes compile, detect-drift, or find-changed-sources
- `ingest/pipeline.py` `_update_existing_page`: entity context insertion uses `re.search(r"^## References", …, re.MULTILINE)` and positional splice instead of `str.replace` — prevents double-injection when LLM-extracted context itself contains `## References`
- `lint/semantic.py` `build_fidelity_context` / `build_completeness_context`: source content now truncated at `QUERY_CONTEXT_MAX_CHARS` (80K) — large books and arXiv PDFs no longer overflow the LLM context window
- `lint/semantic.py` `_group_by_wikilinks`: changed `seen.update(group)` → `seen.add(node)` + added frozenset dedup pass — pages in link chains (A→B→C) were consumed by A's group and skipped; B and C now form their own consistency groups
- `mcp/core.py` `kb_query`: API branch wraps `query_wiki()` in `try/except` — `LLMError`/timeout no longer escapes raw to MCP client
- `mcp/core.py` `kb_ingest_content`: extraction JSON validated before writing the raw file — validation failure no longer leaves an orphaned file on disk
- `mcp/core.py` `kb_save_source`: added `overwrite` parameter (default `false`) with file-existence guard; `write_text` wrapped in `try/except OSError`
- `mcp/quality.py` `kb_refine_page` / `kb_affected_pages` / `kb_save_lint_verdict` / `kb_lint_consistency`: added `_validate_page_id()` guards
- `mcp/quality.py` `kb_create_page`: `source_refs` validated against path traversal before being written to frontmatter
- `review/context.py` `pair_page_with_sources`: added `page_path.resolve().relative_to(wiki_dir.resolve())` guard and `try/except (OSError, UnicodeDecodeError)` around source reads
- `review/refiner.py` `refine_page`: added path traversal guard; normalized CRLF→LF before frontmatter parsing (Windows fix); swapped write order so audit history is persisted before page file
- `utils/llm.py` `call_llm_json`: validates `block.name == tool_name` before returning — wrong-tool responses no longer silently corrupt callers
- `utils/llm.py`: retry loop fixed from `range(MAX_RETRIES)` to `range(MAX_RETRIES + 1)`; `last_error` initialized to avoid `AttributeError` when `MAX_RETRIES=0`
- `utils/wiki_log.py` `append_wiki_log`: replaced `exists()` + `write_text()` with `open("x")` + `FileExistsError` guard — concurrent MCP calls can no longer race on initial log creation
- `evolve/analyzer.py` `find_connection_opportunities`: strips YAML frontmatter before tokenizing — structural keys no longer produce false-positive link suggestions
- `feedback/store.py` `add_feedback_entry`: `page_scores` dict now capped at `MAX_FEEDBACK_ENTRIES` (10k) — previously only `entries` list was capped
- `graph/builder.py` `graph_stats`: `betweenness_centrality` uses `k=min(500, n_nodes)` sampling approximation for graphs > 500 nodes — prevents O(V·E) stall in `kb_evolve` on large wikis
- `utils/pages.py`: inlined `_page_id` helper to break circular import dependency on `kb.graph.builder`
- `evolve/analyzer.py`: bare `except Exception: pass` on feedback lookup narrowed to `logger.warning`
- `config.py`: env override model IDs accepted empty strings; `MAX_FEEDBACK_ENTRIES` and `MAX_VERDICTS` moved from module constants to `kb.config`
- `lint/checks.py`: `check_staleness` silently skipped quoted-string `updated` fields; orphan/isolated detection now exempts `comparisons/` and `synthesis/`; `check_source_coverage` suffix match tightened to avoid false positives on same-named files in different subdirs
- `lint/verdicts.py`: `load_verdicts` now warns on `JSONDecodeError` instead of silently discarding verdict history
- `graph/export.py`: `_sanitize_label` now strips newlines and backticks from Mermaid node labels
- `feedback/reliability.py`: docstring corrected from "below threshold" to "at or below threshold"
- `cli.py`: `mcp` command now has `try/except`; `--type` choices include `comparison` and `synthesis`
- `mcp/browse.py`: `kb_search` and `kb_list_pages` now have outer `try/except`
- `mcp/app.py`: `_format_ingest_result` dead legacy dict-branch for `affected_pages` removed

### Removed
- `scripts/hook_review.py`: deleted — standalone Anthropic-API commit-gate script removed; the `claude -p` skill gate in hooks covers this use case
- `docs/superpowers/specs/2026-04-06-phase2-multi-loop-quality-design.md`: deleted obsolete Phase 2 design spec (fully implemented as of v0.6.0)
- `docs/superpowers/plans/2026-04-06-phase2-multi-loop-quality.md`: deleted obsolete Phase 2 implementation plan (fully shipped)
- `docs/superpowers/plans/2026-04-07-v092-audit-fixes.md`: deleted obsolete v0.9.2 audit-fixes plan
- `docs/superpowers/plans/2026-04-07-v093-remaining-fixes.md`: deleted obsolete v0.9.3 remaining-fixes plan
- `docs/superpowers/plans/2026-04-08-phase393-backlog.md`: deleted — Phase 3.93 plan fully shipped
- `docs/superpowers/plans/2026-04-09-phase394-backlog.md`: deleted — Phase 3.94 plan fully shipped

### Stats
- 651 tests (+38), 25 MCP tools, 12 modules

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
