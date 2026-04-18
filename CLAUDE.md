# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Principles

*(Adapted from [Karpathy's LLM coding observations](https://x.com/karpathy/status/2015883857489522876). Bias toward caution over speed on non-trivial work. For a one-line typo fix, use judgment.)*

**Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**Goal-Driven Execution.** Transform imperative tasks into verifiable goals:
- "Fix the bug" → *"Write a failing test that reproduces it, then make it pass."*
- "Add validation" → *"Write tests for invalid inputs, then make them pass."*
- "Refactor X" → *"Ensure tests pass before and after."*
- For multi-step work, state the plan as `[step] → verify: [check]` — then loop.

**Two tests before declaring done:**
1. *Every changed line should trace directly to the request.* Drop drive-by edits.
2. *Would a senior engineer say this is overcomplicated?* If yes, simplify.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

Current shipped phases and per-cycle tallies live in `CHANGELOG.md` (Quick Reference table at top of `[Unreleased]`). Tool/test/file counts change every cycle — read `CHANGELOG.md` for current numbers, not this file. Open work and deferred-feature roadmap live in `BACKLOG.md`.

### Module Map (`src/kb/`)

- **Core (Phase 1):** `config`, `models`, `utils`, `ingest`, `compile`, `query`, `lint`, `evolve`, `graph`, `mcp` (split package: `app`, `core`, `browse`, `health`, `quality`), `mcp_server` (entry shim), CLI (6 commands: `ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`).
- **Quality (Phase 2):** `feedback` (weighted Bayesian trust — "wrong" penalized 2× vs "incomplete"), `review` (pairing, refiner with audit trail), `lint.semantic` (fidelity / consistency / completeness builders), `lint.verdicts` (persistent verdict store), `.claude/agents/wiki-reviewer.md` (Actor-Critic agent).
- **Capture (Phase 5):** `capture` — conversation/notes atomization for `raw/captures/`.
- **Output adapters (Phase 4.11):** `query.formats` — `markdown`, `marp`, `html`, `chart`, `jupyter`. Files land at `PROJECT_ROOT/outputs/{ts}-{slug}.{ext}` with provenance frontmatter. Outputs directory is **OUTSIDE** `wiki/` (gitignored) to prevent search-index poisoning. `kb_query(output_format=...)` requires `use_api=True`. Chart adapter emits a static Python script + JSON sidecar — matplotlib is NOT a kb runtime dependency.
- **Augment (Phase 5.0):** `lint.fetcher` (DNS-rebind-safe HTTP via `SafeTransport`, allowlists + secret scan + trafilatura + robots.txt). `lint.augment` (three-gate: propose → execute → auto_ingest; G1-G7 eligibility; LLM proposer with abstain; Wikipedia fallback; relevance gate; `[!gap]` callout). `lint._augment_manifest` (atomic JSON state machine). `lint._augment_rate` (file-locked sliding-window: 10/run + 60/hour + 3/host/hour).
- **Phase 3+ research (200+ pages):** DSPy Teacher-Student, RAGAS, Reweave — see `research/agent-architecture-research.md`.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup
cp .env.example .env          # then fill in:
# ANTHROPIC_API_KEY (optional for Claude Code/MCP mode; required for direct API-backed flows), FIRECRAWL_API_KEY (optional), OPENAI_API_KEY (optional)

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

- **`raw/`** — Immutable source documents. The LLM reads but **never modifies** files here (except raw/captures/, which is the sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest). Subdirs: `articles/`, `papers/`, `repos/`, `videos/`, `podcasts/`, `books/`, `datasets/`, `conversations/`, `assets/`. Use Obsidian Web Clipper for web→markdown; download images to `raw/assets/`.
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

**Key APIs** (non-obvious behavior — for full signatures, read the source):
- `call_llm(prompt, tier="write")` / `call_llm_json(prompt, tier, schema)` — In `kb.utils.llm`. Tiers: `scan` (Haiku), `write` (Sonnet), `orchestrate` (Opus). `call_llm_json` uses forced tool_use for guaranteed structured JSON — no fence-stripping needed. Raises `LLMError` on failure, `ValueError` on invalid tier.
- `ingest_source(path, source_type=None, extraction=None, *, defer_small=False, wiki_dir=None)` — In `kb.ingest.pipeline`. Returns dict with `pages_created`, `pages_updated`, `pages_skipped`, `affected_pages`, `wikilinks_injected`, and `duplicate: True` on hash match. Pass `extraction` dict to skip LLM call (Claude Code mode). Pass `wiki_dir` to write to a custom wiki directory (default: `WIKI_DIR`).
- `load_all_pages(wiki_dir=None)` — In `kb.utils.pages`. Returns list of dicts. **Gotcha**: `content_lower` field is pre-lowercased (for BM25), not verbatim.
- `slugify(text)` / `yaml_escape(value)` — In `kb.utils.text`. Single source of truth — imported everywhere, never duplicate.
- `build_extraction_schema(template)` — In `kb.ingest.extractors`. Builds JSON Schema from template fields. `load_template()` is LRU-cached. Use `_build_schema_cached(source_type)` for cached schema lookups (avoids rebuilding on every extraction call).
- `query_wiki(question, wiki_dir=None, max_results=10, conversation_context=None, *, output_format=None)` — In `kb.query.engine`. Returns dict with keys:
  - `answer` (str) — synthesised answer
  - `citations` (list[dict]) — each with `type` (`'wiki'|'raw'`), `path` (str), `context` (str), and a `stale: bool` flag (cycle 4 item #27 doc-sync: surfaced alongside `search_pages` stale flagging so API callers can render `[STALE]` markers inline)
  - `source_pages` (list[str]) — page IDs retrieved before budget trimming
  - `context_pages` (list[str]) — page IDs whose body was packed into the LLM context; empty list on no-match
  - `output_path` + `output_format` — populated when `output_format` is non-text AND the Phase 4.11 adapter succeeded (cycle 4 item #27 doc-sync)
  - `output_error` — populated on adapter failure; absent on success or when `output_format` is empty/text
  `output_format` is keyword-only — additive, zero breakage to existing callers.
- `refine_page(page_id, content, notes)` — In `kb.review.refiner`. Uses regex-based frontmatter split (not YAML parser), rejects content that looks like a frontmatter block (`---\nkey: val\n---`) to prevent corruption.
- `rebuild_vector_index(wiki_dir, force=False)` — In `kb.query.embeddings`. Rebuilds sqlite-vec index from all pages in `wiki_dir`. Gated on (a) module-load-time `_hybrid_available` flag and (b) mtime check (skipped when `force=True`). Called at tail of `ingest_source()`. Batch callers (`compile_wiki`) pass `_skip_vector_rebuild=True` in loop and invoke once at tail.

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
| `orchestrate` | `claude-opus-4-7` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

### Opus 4.7 Behaviour Notes

Applies to orchestrate-tier calls. Added 2026-04-17.
- **Explicit CoT for reasoning-heavy calls.** `call_llm` (in `kb.utils.llm`) does not pass a `thinking={...}` parameter, so extended thinking is never auto-activated at the orchestrate tier — this is true on 4.6 and 4.7 alike. For query synthesis, contradiction detection, `kb_lint_deep`, and semantic reviewers, include "Think step by step before answering" or a structured `## Analysis` scaffold in the prompt.
- **Instruction following is literal.** Prefer positive phrasing ("write prose", "emit JSON") over negative ("don't use lists"). 4.x honours each stated constraint individually; long "don't X, don't Y, don't Z" forbid-lists tend to produce tangential hedging — express constraints as positive actions instead.
- **Minimal formatting remains the default (unchanged from 4.6).** 4.7 avoids bullet-heavy prose, excessive bold/headers, and report-style structure in conversational output. Reserve structure for reference material and lists of ≥4 parallel items.
- **Parallel tool calls preferred** for independent reads — batch `kb_search` + `kb_list_pages` + multi-page `kb_read_page` in one assistant turn rather than serialising.
- **Structured output via `call_llm_json()` (forced tool_use).** Keep using the existing helper in `kb.utils.llm`; it is cache-friendly and removes fence-stripping failure modes. Do not switch to assistant-prefill for JSON.
- **1M-context variant** is available from this runtime (exposed as `claude-opus-4-7[1m]`). For deep multi-source synthesis prefer calling out the capacity in the prompt ("you have ~1M tokens; use the full source text") and handing the subagent raw files directly — routing to the long-context variant is the runtime's job, not the caller's. (Note: `query_wiki`'s 80K-char cap is a library-level constant in `kb.query.engine` that applies to wiki-context assembly, not to direct-prompt pass-through — treat the two as separate concerns.)

### Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (all `SOURCE_TYPE_DIRS` subdirs) for tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

Run `python -m pytest -v` to list all tests (current count tracked in `CHANGELOG.md`). New tests per phase go in versioned files (e.g., `test_v4_11_markdown.py`). Use the `tmp_wiki`/`tmp_project` fixtures for any test that writes files — never write to the real `wiki/` or `raw/` in tests.

### Error Handling Conventions

- **MCP tools**: Return `"Error: ..."` strings on failure — never raise exceptions to the MCP client. Page IDs validated via `_validate_page_id()` (rejects path traversal, verifies path within WIKI_DIR).
- **LLM calls**: Shared retry logic in `_make_api_call()` — 3 attempts with exponential backoff on rate limits/overload/timeout. `LLMError` on exhaustion. `call_llm_json()` uses forced tool_use for guaranteed structured JSON (no fence-stripping needed).
- **Page loading loops**: Catch specific exceptions (not broad `Exception`) and skip with warning — never abort a full scan for one bad file.
- **JSON stores**: All use `atomic_json_write()` (temp file + rename). Capped at 10,000 entries each (feedback, verdicts).
- **Ingest limits**: `MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50` — prevents runaway page creation from hallucinated lists.
- **Path traversal**: Validated at MCP boundary (`_validate_page_id`, ingest path check), at library level (`refine_page`, `pair_page_with_sources`), and in reference extraction. `extract_citations()` and `extract_raw_refs()` reject `..` and leading `/`.
- **Drift pruning**: `compile.compiler.detect_source_drift` persists deletion-pruning to the manifest even though `save_hashes=False` is passed — this is the sole exception to the read-only contract; see function docstring.

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

## Conventions

- All wiki pages must link claims back to specific `raw/` source files. Unsourced claims should be flagged.
- Use `[[wikilinks]]` for inter-page links within `wiki/`.
- Distinguish stated facts (`source says X`) from inferences (`based on A and B, we infer Y`).
- When updating wiki pages, prefer proposing diffs over full rewrites for auditability.
- Keep `wiki/index.md` under 500 lines — use category groupings, one line per page.
- Always install Python packages into the project `.venv`, never globally.

### Evidence Trail Convention

Every wiki page ingested via `ingest_source` grows an `## Evidence Trail` section whose entries `append_evidence_trail` inserts in **reverse-chronological order** (newest event at the top, immediately after a sentinel marker that identifies the section). The convention is load-bearing:

- **Append-only semantics.** Entries below the section are never rewritten; only new entries are prepended after the sentinel. Compiled truth ABOVE the section is still freely rewritten on re-ingest.
- **Reverse chronology, not bottom-append.** Unlike `wiki/log.md` (which appends at the bottom), the evidence trail reads newest-first so a reviewer scanning a long page immediately sees the most recent provenance event. Tools that parse evidence trails for historical timelines should iterate top-down and stop at the sentinel.
- **Sentinel discipline.** The ingest path writes a sentinel line exactly once per page; subsequent appends slip new entries between the sentinel and the previously-newest row. Hand-editing that removes the sentinel defeats append-ordering on the next ingest — treat the sentinel as machine-maintained.
- **When in doubt, trust the file.** Any manual auditor should read the evidence trail as printed; there is no separate index-of-evidence log to reconcile. The file is the ledger.
- **Architecture diagram sync (MANDATORY)**: Source: `docs/architecture/architecture-diagram.html` → Rendered: `docs/architecture/architecture-diagram.png` → Displayed: `README.md`. **Every time the HTML is modified**, you MUST re-render the PNG and commit it. Render command:
  ```python
  # Run from project root with .venv activated
  .venv/Scripts/python -c "
  import asyncio
  from playwright.async_api import async_playwright
  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.launch()
          page = await browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=3)
          await page.goto('file:///D:/Projects/llm-wiki-flywheel/docs/architecture/architecture-diagram.html')
          await page.wait_for_timeout(1500)
          dim = await page.evaluate('() => ({ w: document.body.scrollWidth, h: document.body.scrollHeight })')
          await page.set_viewport_size({'width': dim['w'], 'height': dim['h']})
          await page.wait_for_timeout(500)
          await page.screenshot(path='docs/architecture/architecture-diagram.png', full_page=True, type='png')
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

# Conversation capture (in-session bookmarks, scratch notes, chat transcripts)
# Via MCP: call kb_capture from your client; writes raw/captures/*.md files
# Then: kb_ingest raw/captures/<slug>.md --type capture for each
```

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

Key usage:
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 26 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question, output_format="")` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis. Add `output_format={markdown|marp|html|chart|jupyter}` (requires `use_api=true`) to render the synthesized answer to a file under `outputs/`. `text` or empty = default stdout-only.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction. Output includes `affected_pages` (cascade review list) and `wikilinks_injected` (pages updated with retroactive links). Shows "Duplicate content detected" with hash if source was already ingested.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename, overwrite=false)` — save content to `raw/` for later ingestion. Returns error if file already exists unless `overwrite=true`.
  - `kb_capture(content, provenance=None)` — atomize up to 50KB of unstructured text into discrete `raw/captures/<slug>.md` items via scan-tier LLM. Returns file paths for subsequent `kb_ingest`. Secret-scanner rejects content with API keys, tokens, or private key blocks before any LLM call.
  - `kb_compile_scan(wiki_dir=None)` — find changed sources, then `kb_ingest` each. `wiki_dir` scopes changed-source discovery to that wiki project's sibling `raw/` and `.data/` paths.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint(fix=False, augment=False, dry_run=False, execute=False, auto_ingest=False, max_gaps=5, wiki_dir=None)` — health checks (dead links, orphans, staleness, stub detection, flagged pages). With `augment=True`, runs reactive gap-fill in three opt-in modes: `propose` (default — writes `wiki/_augment_proposals.md`), `execute=True` (fetches URLs to `raw/`), `auto_ingest=True` (pre-extracts at scan tier + ingests with `confidence: speculative`). `wiki_dir` also scopes feedback-derived sections to `<project>/.data/feedback.json`. See `docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md`. Plus `kb_evolve(wiki_dir=None)` (includes coverage gaps + stub enrichment suggestions; feedback gaps are scoped to the wiki project), `kb_detect_drift` (finds wiki pages stale due to raw source changes), `kb_graph_viz` (Mermaid graph export with auto-pruning), `kb_verdict_trends` (weekly quality dashboard).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation History & Roadmap

- **Shipped:** see `CHANGELOG.md` (current cycles) and `CHANGELOG-history.md` (v0.3.0 → v0.10.0 archive). Format: [Keep a Changelog](https://keepachangelog.com/) with Added/Changed/Fixed/Removed.
- **Open work:** see `BACKLOG.md` — severity levels CRITICAL → LOW, grouped by file. Resolved items are deleted (fix recorded in `CHANGELOG.md`); resolved phases collapse to a one-liner under "Resolved Phases".
- **Roadmap (Phase 5 deferred + Phase 6 cut):** see `BACKLOG.md` §"Phase 5 — Community followup proposals" and §"Phase 6 candidates". Includes the 2026-04-13 Karpathy-gist re-evaluation ("RECOMMENDED NEXT SPRINT") and all deferred features (inline claim tags, URL-aware ingest, semantic chunking, typed graph relations, autonomous research loop, etc.).

## Automation

No auto-commit hooks. Doc updates and commits are done manually when ready to push.

### BACKLOG.md lifecycle
Resolved items are **deleted** from `BACKLOG.md` (the fix is recorded in `CHANGELOG.md`). When all items in a phase section are resolved, the section collapses to a one-liner under "Resolved Phases" (e.g., `- **Phase 3.92** — all items resolved in v0.9.11`). This keeps the backlog focused on open work only.

### Doc update checklist (before push)
When asked to update docs, review `git diff` and update as needed:
- `CHANGELOG.md` — add entries under `[Unreleased]`
- `BACKLOG.md` — **delete** resolved items (never strikethrough); collapse empty phase sections
- `CLAUDE.md` — update version numbers, test counts, module/tool counts, API docs
- `README.md` — update if user-facing features or setup changed
- `docs/architecture/architecture-diagram.html` + re-render PNG if architecture changed

All tools are auto-approved for this project (permissions in `settings.local.json`).
