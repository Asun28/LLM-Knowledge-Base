# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

**Phase 3.91 complete (v0.9.10).** 574 tests, 25 MCP tools, 12 modules. Phase 1 core (5 operations + graph + CLI) plus Phase 2 quality system (feedback, review, semantic lint) plus v0.5.0 fixes plus v0.6.0 DRY refactor plus v0.7.0 S+++ upgrade (MCP server split into package, graph PageRank/centrality, entity enrichment on multi-source ingestion, persistent lint verdicts, case-insensitive wikilinks, trust threshold fix, template hash change detection, comparison/synthesis templates, 2 new MCP tools). Plus v0.8.0 BM25 search engine (replaces bag-of-words keyword matching with BM25 ranking — term frequency saturation, inverse document frequency, document length normalization). Plus v0.9.0 hardening release (path traversal protection, citation regex fix, slug collision tracking, JSON fence hardening, MCP error handling, max_results bounds, MCP Phase 2 instructions).

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
- `call_llm(prompt, tier="write")` — Anthropic API wrapper with model tiering, retry (3 attempts, exponential backoff on rate limits/overload/timeout/connection errors), and `LLMError` exception class. Thread-safe singleton client with 120s timeout. Raises `ValueError` on invalid tier. Tiers: `scan` (Haiku), `write` (Sonnet), `orchestrate` (Opus). Defined in `kb.utils.llm`. Shared retry logic in `_make_api_call()`, tier validation in `_resolve_model()`.
- `call_llm_json(prompt, tier, schema)` — Structured output via Claude tool_use. Forced tool choice guarantees valid JSON matching the schema — no fence-stripping or JSON parsing needed. Same retry logic as `call_llm`. In `kb.utils.llm`. Used by `extract_from_source()`.
- `atomic_json_write(data, path)` — Atomic JSON file write (temp file + rename). Creates parent dirs. Used by feedback store, lint verdicts, and review history. In `kb.utils.io`.
- `build_extraction_schema(template)` — Builds JSON Schema from extraction template fields for tool_use. Handles both simple field names and annotated `"field (type): desc"` format. `_parse_field_spec()` (precompiled regex) + `KNOWN_LIST_FIELDS` determine array vs string types. In `kb.ingest.extractors`. `load_template()` is LRU-cached to avoid repeated disk I/O during batch compile.
- `content_hash(path)` — SHA-256, 32-char hex. Accepts `Path | str`. For incremental compile change detection. In `kb.utils.hashing`.
- `make_source_ref(source_path, raw_dir=None)` — Canonical source reference string (`raw/articles/foo.md`). Single source of truth for path→ref conversion. In `kb.utils.paths`.
- `slugify(text)` / `yaml_escape(value)` — URL slug generation and YAML-safe string escaping (handles quotes, backslashes, newlines, tabs, carriage returns, null bytes). In `kb.utils.text`. Single source of truth — imported everywhere, never duplicated.
- `append_wiki_log(operation, message, log_path=None)` — Append timestamped entry to `wiki/log.md` using O(1) file append. Auto-creates the file if missing. In `kb.utils.wiki_log`. Used by ingest, compile, refine.
- `load_all_pages(wiki_dir=None)` — Load all wiki pages with metadata + content. Returns list of dicts with keys: `id`, `path`, `title`, `type`, `confidence`, `sources`, `created`, `updated`, `content`, `raw_content`. In `kb.utils.pages`. Used by query engine and MCP server.
- `normalize_sources(sources)` — Convert frontmatter `source` field (str, list, or None) to `list[str]`. In `kb.utils.pages`. Used everywhere source fields are read.
- `extract_wikilinks(text)` / `extract_raw_refs(text)` — Regex extraction of `[[wikilinks]]` (normalized: stripped, no `.md` suffix) and `raw/...` references (supports `.md`, `.txt`, `.pdf`, `.json`, `.yaml`, `.csv`, `.png`, `.jpg`, `.jpeg`, `.svg`, `.gif`). In `kb.utils.markdown`.
- `load_page(path)` / `validate_frontmatter(post)` — Parse and validate wiki page YAML frontmatter. In `kb.models.frontmatter`. Required fields: `title`, `source`, `created`, `updated`, `type`, `confidence`.
- `ingest_source(path, source_type=None, extraction=None, *, defer_small=False)` — Core ingest function. Accepts optional pre-extracted dict to skip LLM call (used by MCP server in Claude Code mode). Returns dict with keys: `pages_created`, `pages_updated`, `pages_skipped`, `affected_pages` (backlinks + shared-source pages for cascade review), `wikilinks_injected` (pages updated with retroactive wikilinks), and `duplicate: True` when content hash matches an already-ingested source. Automatically calls `inject_wikilinks()` for each newly created page. With `defer_small=True`, sources under `SMALL_SOURCE_THRESHOLD` get summary-only processing. In `kb.ingest.pipeline`.
- `inject_wikilinks(title, target_page_id, wiki_dir=None)` — Scan existing pages for plain-text mentions of a title and inject `[[wikilinks]]`. Word-boundary matching, case-insensitive, skips frontmatter (regex-based split handles `---` inside YAML values). In `kb.compile.linker`.
- `export_mermaid(wiki_dir=None, max_nodes=30)` — Export knowledge graph as Mermaid flowchart. Auto-prunes to most-connected nodes. In `kb.graph.export`.
- `compute_verdict_trends(path=None)` — Analyze verdict history for weekly quality trends. Returns pass rates, period breakdown, trend direction. In `kb.lint.trends`.
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

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

### Model Tiering

| Tier | Model ID | Env Override | Use |
|---|---|---|---|
| `scan` | `claude-haiku-4-5-20251001` | `CLAUDE_SCAN_MODEL` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-4-6` | `CLAUDE_WRITE_MODEL` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-6` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

### Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (4 subdirs) for Phase 2 tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

574 tests across 38 test files — run `python -m pytest -v` to list all. New tests per phase go in versioned files (e.g., `test_v099_phase39.py`). Use the `tmp_wiki`/`tmp_project` fixtures for any test that writes files — never write to the real `wiki/` or `raw/` in tests.

### Error Handling Patterns

All modules use `logging.getLogger(__name__)` for warnings on skipped pages or failed operations.

- **MCP tools**: Return `"Error: ..."` strings on failure — never raise exceptions to the MCP client. All tools wrap external function calls in `try/except` with `logger.error()` (no stack trace leakage to clients). Exception handlers: `kb_stats`, `kb_lint`, `kb_evolve`, `kb_compile_scan`, `kb_lint_consistency`, `kb_affected_pages`. Phase 2 tools (`kb_review_page`, `kb_lint_deep`) catch `FileNotFoundError` specifically, then broad `Exception`. Page ID validation via `_validate_page_id()` before processing — rejects path traversal (`..`, absolute paths) and verifies resolved path stays within WIKI_DIR. All page-reading tools (`kb_read_page`, `kb_create_page`, `kb_review_page`, `kb_lint_deep`) use the shared `_validate_page_id()`. `kb_ingest` validates resolved path stays within `PROJECT_ROOT`. `kb_create_page` validates both `page_type` against `PAGE_TYPES` and `confidence` against `CONFIDENCE_LEVELS`. `max_results` clamped to [1, 100] in `kb_query` and `kb_search`. Extraction JSON validated for required `title`/`name` field. Fail-safe integrations (trust scores in `kb_query`, flagged pages in `kb_lint`) use `try/except` with `logger.debug` since failure is expected when feedback data doesn't exist yet.
- **LLM responses**: `_make_api_call()` provides shared retry logic for both `call_llm()` and `call_llm_json()`. `_resolve_model()` validates tier and returns model ID (shared by both). Retries up to 3 times with exponential backoff on rate limits (`RateLimitError`), overload (500/502/503/529 via `APIStatusError`), connection errors, and timeouts. Raises `LLMError` after exhaustion or on non-retryable errors (401/403). Raises `ValueError` on invalid tier name. Thread-safe singleton client with 120s timeout and `max_retries=0` (disables SDK built-in retries to avoid double retry). `extract_from_source()` uses `call_llm_json()` with forced tool_use for guaranteed structured JSON output — no fence-stripping or JSON parsing needed.
- **Feedback**: `add_feedback_entry()` deduplicates `cited_pages` before trust score updates to prevent inflated scores from duplicate citations.
- **Frontmatter**: `_write_wiki_page()` escapes quotes, backslashes, newlines, tabs, carriage returns, and null bytes via `yaml_escape()`. `_update_existing_page()` checks frontmatter source list (not full-text search) then syncs both YAML `source:` list and References section using `finditer`-based insertion (deterministic last-match targeting). Logs warnings on frontmatter parse failures (specific exceptions: `OSError`, `ValueError`, `AttributeError`, `yaml.YAMLError`). `refine_page()` uses regex-based frontmatter splitting (handles `---` inside content), rejects content starting with `---` (prevents frontmatter corruption). Adds `updated:` field if missing, auto-creates `log.md` if absent.
- **Graph builder**: Only adds edges to nodes that exist in the graph (no dangling edges to nonexistent pages). Catches `OSError`/`UnicodeDecodeError` on `read_text()` and skips unreadable pages with warning.
- **Slugify**: Empty slugify results (all-punctuation names) are skipped with warning logged during entity/concept creation. Slug collisions within a single ingest are detected and logged.
- **Compile**: Manifest saved after each successful source ingest (crash-safe).
- **Page loading loops**: `load_all_pages()` catches specific exceptions (`OSError`, `ValueError`, `TypeError`, `AttributeError`, `yaml.YAMLError`, `UnicodeDecodeError`) — not broad `Exception` — and logs warnings with file path, then continues. Other page-scanning loops (lint checks, graph builder) follow the same pattern.
- **Data retention**: Feedback entries and lint verdicts are capped at 10,000 entries each to prevent unbounded JSON growth. All JSON stores (feedback, verdicts, review history) use `atomic_json_write()` from `kb.utils.io` to prevent corruption from interrupted writes.
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
| `kb_graph_viz(max_nodes)` | Export knowledge graph as Mermaid diagram |
| `kb_verdict_trends()` | Show weekly quality trends from verdict history |

## Conventions

- All wiki pages must link claims back to specific `raw/` source files. Unsourced claims should be flagged.
- Use `[[wikilinks]]` for inter-page links within `wiki/`.
- Distinguish stated facts (`source says X`) from inferences (`based on A and B, we infer Y`).
- When updating wiki pages, prefer proposing diffs over full rewrites for auditability.
- Keep `wiki/index.md` under 500 lines — use category groupings, one line per page.
- Always install Python packages into the project `.venv`, never globally.
- **Architecture diagram sync (MANDATORY)**: Source: `others/architecture-diagram.html` → Rendered: `others/architecture-diagram.png` → Displayed: `README.md` line 9. **Every time the HTML is modified**, you MUST re-render the PNG and commit it. Render command:
  ```python
  # Run from project root with .venv activated
  .venv/Scripts/python -c "
  import asyncio
  from playwright.async_api import async_playwright
  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.launch()
          page = await browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=3)
          await page.goto('file:///D:/Projects/LLM-Knowledge-Base/others/architecture-diagram.html')
          await page.wait_for_timeout(1500)
          dim = await page.evaluate('() => ({ w: document.body.scrollWidth, h: document.body.scrollHeight })')
          await page.set_viewport_size({'width': dim['w'], 'height': dim['h']})
          await page.wait_for_timeout(500)
          await page.screenshot(path='others/architecture-diagram.png', full_page=True, type='png')
          await browser.close()
  asyncio.run(main())
  "
  ```

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
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 25 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question)` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction. Output includes `affected_pages` (cascade review list) and `wikilinks_injected` (pages updated with retroactive links). Shows "Duplicate content detected" with hash if source was already ingested.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename)` — save content to `raw/` for later ingestion.
  - `kb_compile_scan()` — find changed sources, then `kb_ingest` each.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint` (includes flagged pages + stub detection, supports `--fix`), `kb_evolve` (includes coverage gaps + stub enrichment suggestions), `kb_detect_drift` (finds wiki pages stale due to raw source changes), `kb_graph_viz` (Mermaid graph export with auto-pruning), `kb_verdict_trends` (weekly quality dashboard).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation History

See `CHANGELOG.md` for the full phase history (v0.3.0 → v0.9.10).

**Current:** Phase 3.91 (v0.9.10) — 574 tests, 25 MCP tools, 12 modules.

**Phase 3.92 backlog (known issues):**
- ~~`review/refiner.py` missing 10k entry cap on review history~~ — **RESOLVED** (cap applied at `refiner.py:96-97`)
- `kb_read_page`, `kb_list_sources` missing outer `try/except` (raw `OSError`/`PermissionError` can escape to MCP client)
- `fix_dead_links` generates phantom audit trail entries when `re.sub` makes no change
- `inject_wikilinks` `\b` regex silently fails for titles with leading non-word chars (`C++`, `GPT-4o`, `.NET`)
- `compile_wiki` silently drops `pages_skipped`/`wikilinks_injected`/`affected_pages`/`duplicate` from `ingest_source` result
- `evolve/analyzer.py` has no module-level logger; `check_staleness` uses broad `except Exception`; `find_connection_opportunities`/`suggest_new_pages` have unguarded `read_text()` calls
- Hardcoded `0.1` trend threshold in `trends.py` should be `VERDICT_TREND_THRESHOLD` config constant
- `wiki_log.py` calls `stat()` twice on same file; `check_source_coverage` reads each page file twice
- MCP instructions claim 26 tools, actual registered count is 25

**Phase 3.93 backlog (code review 2026-04-08 — new findings):**

*Security / Path Traversal:*
- `mcp/quality.py` `kb_refine_page` missing `_validate_page_id()` before file write — only write-capable MCP tool without traversal protection
- `review/refiner.py` `page_id` not validated against `wiki_dir` at library level before constructing write path
- `review/context.py` `page_id` not validated before `page_path.read_text()` call in `pair_page_with_sources`
- `mcp/quality.py` `kb_affected_pages`, `kb_save_lint_verdict`, `kb_lint_consistency` (comma-split ids) missing `_validate_page_id()` per-element

*MCP Error Handling:*
- `mcp/core.py` `kb_ingest_content` writes raw file to disk before validating extraction JSON — leaves orphaned file on validation failure
- `mcp/core.py` `kb_save_source` `OSError` from `write_text` escapes unhandled to MCP client
- `mcp/core.py` `kb_query` API branch (`query_wiki()` call) has no `try/except` — `LLMError`/timeout escapes to MCP client
- `mcp/core.py` `kb_save_source` silently overwrites existing raw source files (unlike `kb_create_page` which errors)

*Lint Correctness:*
- `lint/runner.py` filter key mismatch: `"dead_links"` (filter) vs `"dead_link"` (issues) — `--fix` never removes fixed errors from report (always-broken since introduction)
- `lint/checks.py` `check_source_coverage` first `read_text()` loop has no error handling; one unreadable file aborts the entire lint run
- `lint/checks.py` `check_source_coverage` suffix-based reference matching (`ref.endswith(f"/{f.name}")`) can false-positive on same-named files across subdirs
- `lint/semantic.py` two unguarded `read_text()` in `_group_by_term_overlap` (line 166) and `build_consistency_context` (line 242)
- `lint/verdicts.py` `load_verdicts` silently discards all verdict history on `JSONDecodeError` with no warning logged

*Query Correctness:*
- `query/engine.py` `query_wiki` never forwards `max_results` to `search_pages` — the [1,100] clamp in `kb_query` is a dead letter in API mode
- `query/engine.py` skip-and-continue context assembly can silently exclude highest-ranked page (too large) while including lower-ranked pages

*Ingest Correctness:*
- `ingest/pipeline.py` summary page always overwritten without checking existence — unlike entity/concept pages which correctly use `_update_existing_page`; loses original `created:` date on re-ingest
- `ingest/pipeline.py` no defense-in-depth path traversal guard: `ingest_source` never verifies `source_path` resolves inside `RAW_DIR` (only MCP layer validates)
- `ingest/pipeline.py` `_update_sources_mapping` and `_update_index_batch` silently no-op when files missing on fresh install (no creation, no warning)

*Compile Correctness:*
- `compile/linker.py` `inject_wikilinks` case mismatch — `target_page_id` not lowercased before `in existing_links` check; `extract_wikilinks` always lowercases, so mixed-case page IDs are never matched as already-linked → duplicate wikilinks injected
- `compile/compiler.py` `find_changed_sources` writes manifest side-effect (saves updated template hashes) even when called read-only from `kb_detect_drift` — suppresses real template changes from next compile scan
- `compile/extractors.py` `load_template` LRU cache never invalidated mid-session — template changes during a running compile are silently ignored

*Graph / Evolve:*
- `graph/export.py` Mermaid label sanitization incomplete — newlines (`\n`) and backticks not stripped; LLM-generated title with newline breaks Mermaid output

*LLM Client:*
- `utils/llm.py` `range(MAX_RETRIES)` yields max 2 retries for `MAX_RETRIES=3` — variable named MAX_RETRIES implies first call + 3 retries; behavior gives first call + 2 retries
- `utils/llm.py` `last_error` is `None` on exhaustion path if `MAX_RETRIES=0` — `raise LLMError(...) from None` silently swallows exception chain

*Utils / Architecture:*
- `utils/pages.py` imports `page_id` from `graph/builder.py` — fragile coupling pulls `networkx` into every page-load operation; broken networkx import disables `load_all_pages` system-wide
- `utils/pages.py` `raw_content` field stores pre-lowercased text — name implies verbatim content; callers expecting original text get silently downcased version
- `MAX_FEEDBACK_ENTRIES` (`feedback/store.py:9`) and `MAX_VERDICTS` (`lint/verdicts.py:9`) defined as module constants, not in `kb.config` alongside `MAX_REVIEW_HISTORY_ENTRIES`

*CLI:*
- `cli.py` `mcp` command missing `try/except` — raw Python traceback shown on startup failure (all other CLI commands handle exceptions cleanly)

*Review Layer:*
- `review/refiner.py` frontmatter regex only matches LF line endings (`---\n`) — CRLF files on Windows silently fail with "Invalid frontmatter format" error
- `review/context.py` `source_path.read_text()` unguarded — `OSError`/`PermissionError` escapes caller

*(Additional findings from 10-part parallel code review, 2026-04-08):*

*CRITICAL — new blockers:*
- `compile/compiler.py` `load_manifest` propagates raw `json.JSONDecodeError` to all callers — one corrupt `.data/hashes.json` crashes `compile_wiki`, `find_changed_sources`, and `detect_source_drift` with no recovery (fix: return `{}` on decode error)
- `ingest/pipeline.py:273` LLM-extracted context strings containing `## References` double-inject the section header via `content.replace("## References", f"{ctx}\n\n## References", 1)`

*HIGH — additional reliability/correctness warnings:*
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

*MEDIUM — additional quality items:*
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

**Phase 4 next:** Two-phase compile pipeline (batch cross-source merging before writing), pre-publish validation gate, iterative multi-hop retrieve/trace loop (BM25 + graph traversal), answer trace enforcement (reject uncited claims), conversation→KB promotion (positively-rated query answers → wiki pages), DSPy Teacher-Student optimization, RAGAS evaluation.

## Automation

Auto-commit hooks are configured in `.claude/settings.local.json`:
- **Stop hook** — When Claude finishes a turn, if there are uncommitted changes and `pytest` passes, auto-commits with `auto: session checkpoint` message.
- **PostToolUse (Bash)** — After any Bash command containing `pytest` with "passed" in output, auto-commits with `auto: tests passed` message.

All tools are auto-approved for this project (permissions in `settings.local.json`).
