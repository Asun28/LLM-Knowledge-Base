# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

**Phase 3.9a complete (v0.9.8).** 519 tests, 23 MCP tools, 12 modules. Phase 1 core (5 operations + graph + CLI) plus Phase 2 quality system (feedback, review, semantic lint) plus v0.5.0 fixes plus v0.6.0 DRY refactor plus v0.7.0 S+++ upgrade (MCP server split into package, graph PageRank/centrality, entity enrichment on multi-source ingestion, persistent lint verdicts, case-insensitive wikilinks, trust threshold fix, template hash change detection, comparison/synthesis templates, 2 new MCP tools). Plus v0.8.0 BM25 search engine (replaces bag-of-words keyword matching with BM25 ranking — term frequency saturation, inverse document frequency, document length normalization). Plus v0.9.0 hardening release (path traversal protection, citation regex fix, slug collision tracking, JSON fence hardening, MCP error handling, max_results bounds, MCP Phase 2 instructions).

**Phase 1 modules:** `kb.config`, `kb.models`, `kb.utils`, `kb.ingest`, `kb.compile`, `kb.query`, `kb.lint`, `kb.evolve`, `kb.graph`, `kb.mcp_server`, CLI (6 commands: `ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`). **MCP server split into `kb.mcp` package** (app, core, browse, health, quality).

**Phase 2 modules:**
- `kb.feedback` — query feedback store (weighted Bayesian trust scoring — "wrong" penalized 2x vs "incomplete"), reliability analysis (flagged pages, coverage gaps)
- `kb.review` — page-source pairing, review context/checklist builder, page refiner (frontmatter-preserving updates with audit trail)
- `kb.lint.semantic` — fidelity, consistency, completeness context builders for LLM-powered evaluation
- `.claude/agents/wiki-reviewer.md` — Actor-Critic reviewer agent definition
- `kb.lint.verdicts` — persistent lint/review verdict storage (pass/fail/warning with audit trail)

**Phase 3+ (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave. Research in `research/agent-architecture-research.md`.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup
cp .env.example .env          # then fill in:
# ANTHROPIC_API_KEY (required), FIRECRAWL_API_KEY (optional), OPENAI_API_KEY (optional)

# Install deps + editable package (enables `kb` CLI command)
# NOTE: `pip install -e .` must be run before `kb` CLI or `from kb import ...` works outside pytest
pip install -r requirements.txt && pip install -e .

# Run all tests
python -m pytest

# Run single test
python -m pytest tests/test_models.py::test_extract_wikilinks -v

# Lint, auto-fix, & format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/

# CLI (after pip install -e .)
kb --version
kb ingest raw/articles/example.md --type article
kb compile [--full]
kb query "What is compile-not-retrieve?"
kb lint [--fix]
kb evolve
kb mcp                        # Start MCP server for Claude Code

# Playwright browser (needed by crawl4ai)
python -m playwright install chromium
```

Ruff config: line length 100, Python 3.12+, rules E/F/I/W/UP (see `pyproject.toml`).

## Architecture

### Three-Layer Content Structure

- **`raw/`** — Immutable source documents. The LLM reads but **never modifies** files here. Subdirs: `articles/`, `papers/`, `repos/`, `videos/`, `podcasts/`, `books/`, `datasets/`, `conversations/`, `assets/`. Use Obsidian Web Clipper for web→markdown; download images to `raw/assets/`.
- **`wiki/`** — LLM-generated and LLM-maintained markdown. Page subdirs: `entities/`, `concepts/`, `comparisons/`, `summaries/`, `synthesis/`. All pages use YAML frontmatter (see template below).
- **`research/`** — Human-authored analysis, project ideas, and meta-research about the knowledge base approach.

### Five Operations Cycle: Ingest → Compile → Query → Lint → Evolve

- **Ingest**: User adds source to `raw/`. LLM reads it, writes summary to `wiki/summaries/`, updates `wiki/index.md`, modifies relevant entity/concept pages, appends to `wiki/log.md`.
- **Compile**: LLM builds/updates interlinked wiki pages. Uses hash-based incremental detection — only processes new/changed sources. Manifest saved after each source (crash-safe). Proposes diffs, not full rewrites.
- **Query**: User asks questions. LLM searches wiki using BM25 ranking (term frequency saturation, IDF weighting, length normalization), synthesizes answers with inline citations to wiki pages and raw sources. Title tokens boosted by `SEARCH_TITLE_WEIGHT` (repeated N times before indexing). Context truncated to 80K chars. Good answers become new wiki pages.
- **Lint**: Health check — orphan pages, dead links, staleness, wikilink cycles, coverage gaps, frontmatter validation. Produces a report, does not silently fix.
- **Evolve**: Gap analysis — what topics lack coverage, what concepts should be linked, what raw sources would fill gaps. User picks suggestions, LLM executes.

### Python Package (`src/kb/`)

Entry point: `kb = "kb.cli:cli"` in `pyproject.toml`. Version in `src/kb/__init__.py`. MCP server entry: `python -m kb.mcp_server` or `kb mcp`. MCP package: `kb.mcp` (split from monolithic `mcp_server.py`).

All paths, model tiers, page types, and confidence levels are defined in `kb.config` — import from there, never hardcode. `PROJECT_ROOT` resolves from `config.py`'s location, so it works regardless of working directory.

**Key APIs:**
- `call_llm(prompt, tier="write")` — Anthropic API wrapper with model tiering, retry (3 attempts, exponential backoff on rate limits/overload/timeout/connection errors), and `LLMError` exception class. Thread-safe singleton client with 120s timeout. Raises `ValueError` on invalid tier. Tiers: `scan` (Haiku), `write` (Sonnet), `orchestrate` (Opus). Defined in `kb.utils.llm`. Shared retry logic in `_make_api_call()`.
- `call_llm_json(prompt, tier, schema)` — Structured output via Claude tool_use. Forced tool choice guarantees valid JSON matching the schema — no fence-stripping or JSON parsing needed. Same retry logic as `call_llm`. In `kb.utils.llm`. Used by `extract_from_source()`.
- `build_extraction_schema(template)` — Builds JSON Schema from extraction template fields for tool_use. Handles both simple field names and annotated `"field (type): desc"` format. `_parse_field_spec()` + `KNOWN_LIST_FIELDS` determine array vs string types. In `kb.ingest.extractors`.
- `content_hash(path)` — SHA-256, 32-char hex. Accepts `Path | str`. For incremental compile change detection. In `kb.utils.hashing`.
- `make_source_ref(source_path, raw_dir=None)` — Canonical source reference string (`raw/articles/foo.md`). Single source of truth for path→ref conversion. In `kb.utils.paths`.
- `slugify(text)` / `yaml_escape(value)` — URL slug generation and YAML-safe string escaping (handles quotes, backslashes, newlines, tabs, carriage returns, null bytes). In `kb.utils.text`. Single source of truth — imported everywhere, never duplicated.
- `append_wiki_log(operation, message, log_path=None)` — Append timestamped entry to `wiki/log.md` using O(1) file append. Auto-creates the file if missing. In `kb.utils.wiki_log`. Used by ingest, compile, refine.
- `load_all_pages(wiki_dir=None)` — Load all wiki pages with metadata + content. Returns list of dicts with keys: `id`, `path`, `title`, `type`, `confidence`, `sources`, `created`, `updated`, `content`, `raw_content`. In `kb.utils.pages`. Used by query engine and MCP server.
- `normalize_sources(sources)` — Convert frontmatter `source` field (str, list, or None) to `list[str]`. In `kb.utils.pages`. Used everywhere source fields are read.
- `extract_wikilinks(text)` / `extract_raw_refs(text)` — Regex extraction of `[[wikilinks]]` (normalized: stripped, no `.md` suffix) and `raw/...` references. In `kb.utils.markdown`.
- `load_page(path)` / `validate_frontmatter(post)` — Parse and validate wiki page YAML frontmatter. In `kb.models.frontmatter`. Required fields: `title`, `source`, `created`, `updated`, `type`, `confidence`.
- `ingest_source(path, source_type=None, extraction=None)` — Core ingest function. Accepts optional pre-extracted dict to skip LLM call (used by MCP server in Claude Code mode). In `kb.ingest.pipeline`.
- `add_verdict(page_id, verdict_type, verdict, issues, notes)` — Store lint/review verdict persistently. In `kb.lint.verdicts`.
- `get_verdict_summary()` — Aggregate verdict statistics. In `kb.lint.verdicts`.
- `BM25Index(documents)` / `index.score(query_tokens, k1, b)` — BM25 ranking index. In `kb.query.bm25`.
- `tokenize(text)` — BM25-aware tokenizer (stopword filtering, hyphen preservation). In `kb.query.bm25`.
- `WikiPage` / `RawSource` — Dataclasses in `kb.models.page`.

### Wiki Index Files

| File | Purpose |
|---|---|
| `wiki/index.md` | Master catalog, one-line per page, under 500 lines |
| `wiki/_sources.md` | Raw source → wiki page mapping (traceability for lint) |
| `wiki/_categories.md` | Auto-maintained category tree |
| `wiki/log.md` | Append-only chronological record of all operations |
| `wiki/contradictions.md` | Explicit tracker for conflicting claims across sources |

### Model Tiering

| Tier | Model ID | Use |
|---|---|---|
| `scan` | `claude-haiku-4-5-20251001` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-4-6` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-6` | Orchestration, query answering, verification — highest reasoning |

### Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (4 subdirs) for Phase 2 tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

519 tests across 36 test files. Core tests: `test_compile.py` (11), `test_evolve.py` (11), `test_graph.py` (8), `test_ingest.py` (8), `test_lint.py` (14), `test_models.py` (4), `test_query.py` (12), `test_cli.py` (5). Phase 2 tests: `test_feedback.py` (14), `test_review.py` (16), `test_lint_semantic.py` (8), `test_mcp_phase2.py` (10). Fix/upgrade tests: `test_fixes_v050.py` (21), `test_fixes_v060.py` (31), `test_utils.py` (33), `test_v070.py` (28), `test_bm25.py` (19), `test_v090.py` (43). v0.9.1 tests: `test_llm.py` (27), `test_lint_verdicts.py` (12), `test_paths.py` (6), `test_mcp_browse_health.py` (15), `test_mcp_core.py` (14), `test_mcp_quality_new.py` (12). v0.9.2 tests: `test_ingest_fixes_v092.py` (8), `test_lint_query_fixes_v092.py` (12), `test_validation_fixes_v092.py` (11). v0.9.3 tests: `test_compiler_mcp_v093.py` (11), `test_lint_fix_v093.py` (6). v0.9.4 tests: `test_tier1_fixes_v094.py` (8), `test_stub_detection_v094.py` (6), `test_drift_detection_v094.py` (7). v0.9.5 tests: `test_tier1_audit_v095.py` (13). v0.9.6 tests: `test_tier2_audit_v096.py` (18). v0.9.7 tests: `test_tier3_fixes_v097.py` (7). v0.9.8 tests: `test_v098_fixes.py` (29).

### Error Handling Patterns

All modules use `logging.getLogger(__name__)` for warnings on skipped pages or failed operations.

- **MCP tools**: Return `"Error: ..."` strings on failure — never raise exceptions to the MCP client. All tools wrap external function calls in `try/except` with `logger.error()` (no stack trace leakage to clients). Exception handlers: `kb_stats`, `kb_lint`, `kb_evolve`, `kb_compile_scan`, `kb_lint_consistency`, `kb_affected_pages`. Phase 2 tools (`kb_review_page`, `kb_lint_deep`) catch `FileNotFoundError` specifically, then broad `Exception`. Page ID validation via `_validate_page_id()` before processing — rejects path traversal (`..`, absolute paths) and verifies resolved path stays within WIKI_DIR. All page-reading tools (`kb_read_page`, `kb_create_page`, `kb_review_page`, `kb_lint_deep`) use the shared `_validate_page_id()`. `kb_ingest` validates resolved path stays within `PROJECT_ROOT`. `kb_create_page` validates both `page_type` against `PAGE_TYPES` and `confidence` against `CONFIDENCE_LEVELS`. `max_results` clamped to [1, 100] in `kb_query` and `kb_search`. Extraction JSON validated for required `title`/`name` field. Fail-safe integrations (trust scores in `kb_query`, flagged pages in `kb_lint`) use `try/except` with `logger.debug` since failure is expected when feedback data doesn't exist yet.
- **LLM responses**: `_make_api_call()` provides shared retry logic for both `call_llm()` and `call_llm_json()`. Retries up to 3 times with exponential backoff on rate limits, overload (429/500/502/503/529), connection errors, and timeouts. Raises `LLMError` after exhaustion or on non-retryable errors (401/403). Raises `ValueError` on invalid tier name. Thread-safe singleton client with 120s timeout and `max_retries=0` (disables SDK built-in retries to avoid double retry). `extract_from_source()` uses `call_llm_json()` with forced tool_use for guaranteed structured JSON output — no fence-stripping or JSON parsing needed.
- **Feedback**: `add_feedback_entry()` deduplicates `cited_pages` before trust score updates to prevent inflated scores from duplicate citations.
- **Frontmatter**: `_write_wiki_page()` escapes quotes, backslashes, newlines, tabs, carriage returns, and null bytes via `yaml_escape()`. `_update_existing_page()` checks frontmatter source list (not full-text search) then syncs both YAML `source:` list and References section using `finditer`-based insertion (deterministic last-match targeting). Logs warnings on frontmatter parse failures (specific exceptions: `OSError`, `ValueError`, `AttributeError`, `yaml.YAMLError`). `refine_page()` uses regex-based frontmatter splitting (handles `---` inside content), rejects content starting with `---` (prevents frontmatter corruption). Adds `updated:` field if missing, auto-creates `log.md` if absent.
- **Graph builder**: Only adds edges to nodes that exist in the graph (no dangling edges to nonexistent pages). Catches `OSError`/`UnicodeDecodeError` on `read_text()` and skips unreadable pages with warning.
- **Slugify**: Empty slugify results (all-punctuation names) are skipped with warning logged during entity/concept creation. Slug collisions within a single ingest are detected and logged.
- **Compile**: Manifest saved after each successful source ingest (crash-safe).
- **Page loading loops**: `load_all_pages()` catches specific exceptions (`OSError`, `ValueError`, `TypeError`, `AttributeError`, `yaml.YAMLError`, `UnicodeDecodeError`) — not broad `Exception` — and logs warnings with file path, then continues. Other page-scanning loops (lint checks, graph builder) follow the same pattern.
- **Data retention**: Feedback entries and lint verdicts are capped at 10,000 entries each to prevent unbounded JSON growth. Both stores use atomic writes (temp file + rename) to prevent corruption from interrupted writes.
- **Ingest limits**: `MAX_ENTITIES_PER_INGEST=50` and `MAX_CONCEPTS_PER_INGEST=50` prevent runaway page creation from hallucinated entity lists. Excess items truncated with warning logged.
- **Citation safety**: `extract_citations()` rejects paths containing `..` or starting with `/` to prevent path traversal in LLM-generated answers.
- **Feedback validation**: `add_feedback_entry()` enforces length limits — question/notes max 2000 chars, page ID max 200 chars, max 50 cited pages. Rejects path traversal patterns (`..`, leading `/`) in page IDs.
- **Verdict validation**: `add_verdict()` validates issue severity against `VALID_SEVERITIES = ("error", "warning", "info")` — rejects unknown severities. Each issue must be a dict.
- **Source path validation**: `pair_page_with_sources()` validates source paths from frontmatter stay within the project root (blocks `../..` traversal and absolute paths).

## Phase 2 Workflows

### Standard Ingest (with Self-Refine)
1. `kb_ingest(path)` — get extraction prompt
2. Extract JSON — `kb_ingest(path, extraction_json)`
3. For each created page: `kb_review_page(page_id)` — self-critique
4. If issues: `kb_refine_page(page_id, updated_content)` (max 2 rounds)

### Thorough Ingest (with Actor-Critic)
1-4. Same as Standard Ingest
5. Spawn wiki-reviewer agent with created page_ids
6. Review findings — fix or accept
7. `kb_affected_pages` — flag related pages

### Deep Lint
1. `kb_lint()` — mechanical report
2. For errors: `kb_lint_deep(page_id)` — evaluate fidelity
3. Fix issues via `kb_refine_page`
4. `kb_lint_consistency()` — contradiction check
5. Re-run `kb_lint()` to verify (max 3 rounds)

### Query with Feedback
1. `kb_query(question)` — synthesize answer
2. After user reaction: `kb_query_feedback(question, rating, pages)`

### Phase 2 MCP Tools
| Tool | Purpose |
|------|---------|
| `kb_review_page(page_id)` | Page + sources + checklist for quality review |
| `kb_refine_page(page_id, content, notes)` | Update page preserving frontmatter |
| `kb_lint_deep(page_id)` | Source fidelity check context |
| `kb_lint_consistency(page_ids)` | Cross-page contradiction check |
| `kb_query_feedback(question, rating, pages, notes)` | Record query success/failure |
| `kb_reliability_map()` | Page trust scores from feedback |
| `kb_affected_pages(page_id)` | Pages affected by a change |
| `kb_save_lint_verdict(page_id, verdict_type, verdict, issues, notes)` | Record lint/review verdict persistently |
| `kb_create_page(page_id, title, content, page_type, confidence, source_refs)` | Create comparison/synthesis/any wiki page |

## Conventions

- All wiki pages must link claims back to specific `raw/` source files. Unsourced claims should be flagged.
- Use `[[wikilinks]]` for inter-page links within `wiki/`.
- Distinguish stated facts (`source says X`) from inferences (`based on A and B, we infer Y`).
- When updating wiki pages, prefer proposing diffs over full rewrites for auditability.
- Keep `wiki/index.md` under 500 lines — use category groupings, one line per page.
- Always install Python packages into the project `.venv`, never globally.

## Wiki Page Frontmatter Template

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-05
updated: 2026-04-05
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
---
```

## Ingestion Commands

```bash
# Web page → markdown (heavy, JavaScript-rendered pages)
crwl URL -o markdown > raw/articles/page-name.md

# Web page → markdown (lightweight, articles/blogs — faster)
trafilatura -u URL > raw/articles/page-name.md

# PDF/DOCX → markdown (simple documents)
markitdown file.pdf > raw/papers/paper-name.md

# PDF → markdown (complex documents with tables/figures)
docling file.pdf --output raw/papers/

# YouTube transcript
yt-dlp --write-auto-sub --skip-download URL -o raw/videos/video-name

# arXiv paper (Python)
# import arxiv; paper = next(arxiv.Client().results(arxiv.Search(id_list=["2401.12345"])))
```

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

Key usage:
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 21 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question)` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename)` — save content to `raw/` for later ingestion.
  - `kb_compile_scan()` — find changed sources, then `kb_ingest` each.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint` (includes flagged pages + stub detection, supports `--fix`), `kb_evolve` (includes coverage gaps + stub enrichment suggestions), `kb_detect_drift` (finds wiki pages stale due to raw source changes).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation Phases

- **Phase 1 (complete, v0.3.0):** Content-hash incremental compile, three index files, model tiering, structured lint output, 5 operations + graph + CLI.
- **Phase 2 (complete, v0.4.0):** Multi-loop supervision for Lint, Actor-Critic compile, query feedback loop, Self-Refine on Compile. 7 new MCP tools, 3 new modules, wiki-reviewer agent.
- **Phase 2.1 (complete, v0.5.0):** Quality and robustness fixes — weighted Bayesian trust scoring (wrong penalized 2x), canonical path utilities (`make_source_ref`, `_canonical_rel_path`), YAML injection protection, extraction JSON validation, regex-based frontmatter parsing, graph edge invariant enforcement, empty slug guards, config-driven tuning constants (`STALENESS_MAX_DAYS`, `SEARCH_TITLE_WEIGHT`, etc.), improved MCP error handling with logging.
- **Phase 2.2 (complete, v0.6.0):** DRY refactor and code quality — shared utilities (`kb.utils.text`, `kb.utils.wiki_log`, `kb.utils.pages`) eliminated all code duplication (slugify 2x→1x, page loading 2x→1x, log appending 4x→1x, page_id 3x→1x). MCP server's `_apply_extraction` (80 lines) replaced by `ingest_source(extraction=...)`. Source type whitelist validation in extractors. `normalize_sources()` ensures consistent list format across all modules. YAML escape extended for newlines/tabs. Auto-create wiki/log.md on first write. Consolidated test fixtures (`create_wiki_page`, `create_raw_source`). 33 new parametrized edge case tests (180 total).
- **Phase 2.3 (complete, v0.7.0):** S+++ upgrade — MCP server split into `kb.mcp` package (5 modules from 810-line monolith), graph analysis with PageRank and betweenness centrality, entity/concept enrichment on multi-source ingestion, persistent lint verdict storage with audit trail, case-insensitive wikilink resolution, trust threshold boundary fix (< to <=), template hash change detection for compile, comparison/synthesis extraction templates, 2 new MCP tools (`kb_create_page`, `kb_save_lint_verdict`). 21 MCP tools, 234 tests.
- **Phase 3.0 (complete, v0.8.0):** BM25 search engine — replaced naive bag-of-words keyword matching with BM25 ranking algorithm (term frequency saturation, inverse document frequency, document length normalization). Title boosting via token repetition. Configurable BM25_K1/BM25_B parameters. Custom tokenizer with stopword filtering and hyphen preservation. NOT RAG — searches pre-compiled wiki pages, not raw chunks. 252 tests.
- **Phase 3.1 (complete, v0.9.0):** Hardening release — path traversal protection in `_validate_page_id()`, `kb_read_page`, `kb_create_page` (rejects `..` and absolute paths, verifies resolved path within WIKI_DIR). Citation regex fix (underscore support in page IDs). Slug collision tracking (`pages_skipped` in ingest result). JSON fence hardening (handles single-line `` ```json{...}``` ``). MCP error handling (all tools wrap external calls in try/except). `max_results` bounds [1, 100] in `kb_query`/`kb_search`. MCP instructions updated with Phase 2 tools. Anthropic SDK double-retry fix (`max_retries=0` on client). Redundant `.removesuffix(".md")` removed from linker/graph (already done by `extract_wikilinks`). 289 tests.
- **Phase 3.2 (complete, v0.9.1):** Comprehensive audit and hardening — BM25 division-by-zero fix (avgdl=0 guard), source path traversal protection in `pair_page_with_sources()`, thread-safe LLM client singleton (double-check locking), `ValueError` on invalid tier, O(1) wiki log append (replaces O(n) read-modify-write), narrowed exception handling in `load_all_pages()` (specific types, not broad `Exception`), frontmatter-aware source collision detection in `_update_existing_page()`, consistent `_validate_page_id()` usage across all MCP tools, confidence level validation in `kb_create_page`, `yaml_escape` handles `\r` and `\0`, feedback/verdict 10k entry retention limits, duplicate "could" removed from semantic lint. Test coverage: 93 new tests (289→382) across 6 new test files — `test_llm.py` (27, LLM retry logic), `test_lint_verdicts.py` (12, verdict storage), `test_paths.py` (6, canonical paths), `test_mcp_browse_health.py` (15, browse/health tools), `test_mcp_core.py` (14, core tools), `test_mcp_quality_new.py` (12, quality tools). MCP tool test coverage 41%→95%.
- **Phase 3.3 (complete, v0.9.2):** Audit fixes — 15 bug fixes, 32 new tests (382→414). Ingest pipeline: fixed flawed regex in `_update_existing_page()` (replaced negative lookahead with `finditer` last-match approach), added logging to silent exception handler (specific types instead of bare `except`), surfaced `pages_skipped` in CLI and MCP output. Semantic lint: removed domain terms from `common_words` stoplist ("entity", "concept", etc.), fixed consistency group truncation (chunks instead of silent discard). Query engine: added context truncation logging, BM25 avgdl guard logging. MCP: case-insensitive page lookup now validates resolved path stays in WIKI_DIR, `logger.exception` → `logger.error` in health tools. Input validation: feedback store enforces length limits (question/notes 2000 chars, page ID 200 chars, max 50 cited pages, path traversal rejection), verdict severity validation (`error`/`warning`/`info`), refiner rejects content starting with `---`. Config: dev dependencies added to pyproject.toml.
- **Phase 3.4 (complete, v0.9.3):** Feature completion — `kb_compile` MCP tool (22nd tool, calls `compile_wiki()` for full API-driven compilation), `kb lint --fix` implementation (auto-fixes dead links by replacing broken `[[wikilinks]]` with plain text, plumbed through runner and CLI), `MAX_SEARCH_RESULTS` config constant (replaces hardcoded 100 in `kb_query`/`kb_search`), manifest behavior verified with tests. 17 new tests (414→431).
- **Phase 3.5 (complete, v0.9.4):** Tier 1-3 improvements — `build_backlinks()` now filters broken links (consistent with `build_graph()`), `analyze_coverage()` uses `parent.name` instead of fragile string containment, redundant `.removesuffix(".md")` removed from evolve, JSON fence stripping handles whitespace. Stub page detection in lint (`check_stub_pages()` — flags pages with <100 chars body, skips summaries) integrated into `run_all_checks()` and evolve recommendations. Content drift detection (`detect_source_drift()`) finds wiki pages stale due to raw source changes, new `kb_detect_drift` MCP tool (23rd tool). 21 new tests (431→452).
- **Phase 3.8 (complete, v0.9.7):** Tier-3 fixes and observability — query search logs debug when falling back to raw terms (all stopwords), `kb_affected_pages` uses `debug` instead of `warning` for expected shared-sources failure, `LLMError` messages now distinguish error types (timeout, rate limit, connection, server error with status code). 7 new tests (483→490).
- **Phase 3.7 (complete, v0.9.6):** Tier-2 audit hardening — query context skips whole pages instead of truncating mid-page (preserves markdown structure), atomic writes for feedback/verdict stores (temp file + rename), empty query validation in `kb_search`, entity/concept count limit per ingest (`MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50`), citation path traversal validation (rejects `..` and leading `/`), bare except logging in `kb_refine_page`, evolve surfaces low-trust pages from feedback (`flagged_pages` in report + recommendation). 18 new tests (465→483).
- **Phase 3.6 (complete, v0.9.5):** Tier-1 audit hardening — extraction data type validation in ingest pipeline (`isinstance` guard for `entities_mentioned`/`concepts_mentioned`), `UnicodeDecodeError` handling in graph builder (`build_graph()` skips unreadable pages instead of crashing), empty title validation in `kb_create_page`, MCP instructions string updated with 3 missing tools (`kb_compile`, `kb_detect_drift`, `kb_save_source`), evolve stub check logs on failure instead of silent `pass`, `fix_dead_links()` writes audit trail to `wiki/log.md`. 13 new tests (452→465).
- **Phase 3.9a (complete, v0.9.8):** Deep audit fixes and structured outputs — `kb_ingest` path traversal protection (validates resolved path stays within `PROJECT_ROOT`), `call_llm_json()` structured output via Claude tool_use (forced tool choice guarantees valid JSON, eliminates 13 lines of fence-stripping/JSON parsing), `build_extraction_schema()` + `_parse_field_spec()` for template→JSON Schema conversion (handles both simple and annotated field formats, `KNOWN_LIST_FIELDS` set for type inference), `_make_api_call()` shared retry helper (extracted from `call_llm`, used by both `call_llm` and `call_llm_json`), feedback trust score deduplication (`cited_pages` deduplicated before scoring to prevent inflated trust), atomic writes for review history (tempfile+rename pattern matching feedback/verdict stores). 29 new tests (490→519) in `test_v098_fixes.py` — path traversal (5), `call_llm_json` (6), schema builder (4), field spec parser (6), feedback dedup (2), atomic writes (4), shared retry (2).
- **Phase 3.9 (planned):** Infrastructure for content growth and AI leverage — semantic lint for orphan pages (consistency checks on isolated pages), verdict trend dashboard MCP tool (`kb_verdict_trends` — show quality improvement over time), MCP Prompts for extraction workflows (expose templates as reusable prompts to speed ingestion). PageRank-blended search ranking (blend BM25 score with PageRank: `final_score = bm25_score * (1 + weight * pagerank_normalized)` — graph features currently computed but unused in ranking). Duplicate detection in ingest (hash-based dedup in `ingest_source()` — check if content_hash already exists in `_sources.md`, promoted from Phase 4). Pydantic validation for extraction schemas (create models per template, validate in `extract_from_source()` before returning, promoted from Phase 4). arxiv MCP integration in paper ingest (when `arxiv_id` is extracted, fetch metadata/citations from arxiv MCP server, cross-reference cited papers against existing wiki). Environment-configurable model tiers (`CLAUDE_SCAN_MODEL`, `CLAUDE_WRITE_MODEL`, `CLAUDE_ORCHESTRATE_MODEL` env vars). Template field name standardization (normalize `author`/`authors`/`speakers`/`participants` across all templates). Inspired by llm-wiki-compiler: semantic dependency tracking in compile (reverse map of concepts→sources — when source A changes, auto-recompile unchanged sources that share concepts with A, preventing stale cross-references), source deletion workflow (frozen slugs pattern — when raw source is removed, shared concept pages are preserved/frozen, exclusively-owned pages marked orphaned, clean lifecycle management), retroactive inbound wikilink injection (rule-based two-pass resolver — when new page is created, scan all existing pages for mentions of the new title and inject `[[wikilinks]]` using word-boundary matching, no LLM calls needed). Inspired by karpathy-llm-wiki: cascade update on ingest (after ingesting a new source, automatically identify and update affected wiki pages — makes `kb_affected_pages` actionable instead of passive/report-only), See Also auto-maintenance in lint `--fix` (expand auto-fix to add missing cross-references and remove dead See Also links, not just dead wikilinks), inline conflict annotation (when sources contradict, annotate disagreements within the article with source attribution instead of only logging to `wiki/contradictions.md`). Inspired by llm-wiki-skill: Mermaid graph export with smart pruning (`kb_graph_viz` MCP tool / `kb graph --mermaid` CLI — render knowledge graph as Mermaid diagram, auto-prune to top 30 most-connected nodes when >50 total, compatible with Obsidian/GitHub/VS Code), URL-based smart routing on ingest (auto-detect URL domain and route to best extractor — youtube.com→yt-dlp transcript, twitter.com→thread capture, arxiv.org→paper download, default→trafilatura with crwl fallback — eliminates manual tool selection), content-length-aware ingest tiering (sources <1000 chars get simplified processing — summary only, entity/concept mentions use `[deferred]` markers instead of creating stub pages, prevents stub proliferation at ingest time rather than detecting post-hoc in lint).
- **Phase 4 (200+ pages):** Scale and optimization — BM25 parameter tuning (needs content volume for recall/precision measurement), rollback mechanism for partial ingest failures. Two-phase compile pipeline (separate concept extraction from page generation across all sources before writing — enables batch cross-source merging and fail-before-write; inspired by llm-wiki-compiler). DSPy Teacher-Student optimization, RAGAS evaluation, Reweave (backward propagation of new knowledge through existing pages). Inspired by DocMason: pre-publish validation gate (compile-time quality check before pages land in wiki/ — reject/quarantine on bad frontmatter, missing sources, stub content, broken wikilinks), iterative retrieve/trace loop (multi-hop query using BM25 + graph link traversal → re-rank → synthesize), answer trace enforcement (end-to-end provenance chain — reject uncited claims as a hard gate), structured knowledge index (`knowledge.json` — persistent machine-readable entity/relation/metadata export from graph module), conversation→KB promotion (auto-create wiki pages from positively-rated query answers via feedback store + `kb_create_page` — archived answers use frozen page type exempt from cascade updates; inspired by karpathy-llm-wiki). Inspired by karpathy-llm-wiki: date-slug raw source naming validation (enforce/suggest `YYYY-MM-DD-slug.md` naming on ingest — creates implicit timeline, aids staleness detection).

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

## Automation

Auto-commit hooks are configured in `.claude/settings.local.json`:
- **Stop hook** — When Claude finishes a turn, if there are uncommitted changes and `pytest` passes, auto-commits with `auto: session checkpoint` message.
- **PostToolUse (Bash)** — After any Bash command containing `pytest` with "passed" in output, auto-commits with `auto: tests passed` message.

All tools are auto-approved for this project (permissions in `settings.local.json`).
