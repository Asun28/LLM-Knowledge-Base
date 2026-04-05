# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Status:** Scaffolded — `raw/`, `wiki/`, and `src/kb/` package are in place with CLI skeleton. Operation implementations (ingest, compile, query, lint, evolve) are stubbed but not yet wired up. The utility layer (`config`, `models`, `utils`) is functional and tested.

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup (ANTHROPIC_API_KEY required for LLM operations)
cp .env.example .env          # then fill in API keys

# Install deps + editable package (enables `kb` CLI command)
# NOTE: `pip install -e .` must be run before `kb` CLI or `from kb import ...` works outside pytest
pip install -r requirements.txt && pip install -e .

# Run all tests
python -m pytest

# Run single test
python -m pytest tests/test_models.py::test_extract_wikilinks -v

# Lint & format
ruff check src/ tests/
ruff format src/ tests/

# CLI
kb --version
kb ingest raw/articles/example.md --type article
kb compile [--full]
kb query "What is compile-not-retrieve?"
kb lint [--fix]
kb evolve

# Playwright browser (needed by crawl4ai)
python -m playwright install chromium
```

Ruff config: line length 100, Python 3.12+, rules E/F/I/W/UP (see `pyproject.toml`).

## Architecture

### Three-Layer Content Structure

- **`raw/`** — Immutable source documents. The LLM reads but **never modifies** files here. Subdirs: `articles/`, `papers/`, `repos/`, `videos/`, `podcasts/`, `books/`, `datasets/`, `conversations/`, `assets/`. Use Obsidian Web Clipper for web→markdown; download images to `raw/assets/`.
- **`wiki/`** — LLM-generated and LLM-maintained markdown. Page subdirs: `entities/`, `concepts/`, `comparisons/`, `summaries/`, `synthesis/`. All pages use YAML frontmatter (see template below).
- **`research/`** — Human-authored analysis, project ideas, and meta-research about the knowledge base approach.

### Wiki Index Files

| File | Purpose |
|---|---|
| `wiki/index.md` | Master catalog, one-line per page, under 500 lines |
| `wiki/_sources.md` | Raw source → wiki page mapping (traceability for lint) |
| `wiki/_categories.md` | Auto-maintained category tree |
| `wiki/log.md` | Append-only chronological record of all operations |
| `wiki/contradictions.md` | Explicit tracker for conflicting claims across sources |

### Python Package (`src/kb/`)

The `kb` package mirrors the five operations as sub-packages:

- **`kb.config`** — All paths, model tiers, constants. Single source of truth for directory layout.
- **`kb.cli`** — Click-based CLI: `kb ingest|compile|query|lint|evolve`
- **`kb.ingest/`** — `pipeline.py` (orchestrator), `extractors.py` (per-source-type extraction)
- **`kb.compile/`** — `compiler.py` (orchestrator), `differ.py` (diff-based updates), `linker.py` (wikilink cross-referencing)
- **`kb.query/`** — `engine.py` (search + synthesize), `citations.py` (provenance tracking)
- **`kb.lint/`** — `runner.py` (orchestrator), `checks.py` (orphans, dead links, staleness, circular refs, coverage gaps)
- **`kb.evolve/`** — `analyzer.py` (gap analysis, connection discovery, source suggestions)
- **`kb.models/`** — `page.py` (`WikiPage`, `RawSource` dataclasses), `frontmatter.py` (validation via `python-frontmatter`)
- **`kb.graph/`** — `builder.py` (networkx from wikilinks), `visualize.py` (pyvis interactive graph)
- **`kb.utils/`** — `hashing.py` (SHA-256 for incremental compile), `markdown.py` (wikilink/ref extraction), `llm.py` (Anthropic API with model tiering)

### Model Tiering

| Tier | Model ID | Use |
|---|---|---|
| `scan` | `claude-haiku-4-5-20251001` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-4-6` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-6` | Orchestration, query answering, verification — highest reasoning |

Call via `call_llm(prompt, tier="write")` from `kb.utils.llm`. Model IDs defined in `kb.config.MODEL_TIERS`.

### Extraction Templates (`templates/`)

YAML schemas per source type (article, paper, video, repo, podcast, book, dataset, conversation). Each defines `extract:` fields and `wiki_outputs:` mapping to wiki subdirectories. Used by the ingest pipeline to drive consistent extraction.

## Operations

Five operations in a cycle: **Ingest → Compile → Query → Lint → Evolve**

- **Ingest**: User adds source to `raw/`. LLM reads it, writes summary to `wiki/summaries/`, updates `wiki/index.md`, modifies relevant entity/concept pages, appends to `wiki/log.md`.
- **Compile**: LLM builds/updates interlinked wiki pages. Uses hash-based incremental detection — only processes new/changed sources. Proposes diffs, not full rewrites.
- **Query**: User asks questions. LLM searches wiki, synthesizes answers with inline citations to wiki pages and raw sources. Good answers become new wiki pages.
- **Lint**: Health check — orphan pages, dead links, staleness, circular reasoning, coverage gaps, frontmatter validation. Produces a report, does not silently fix.
- **Evolve**: Gap analysis — what topics lack coverage, what concepts should be linked, what raw sources would fill gaps. User picks suggestions, LLM executes.

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
title: Page Title
source:
  - raw/articles/source-file.md
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

## Key Dependencies

**Core (active now):**
- `anthropic` — Claude API for compile/query/lint operations
- `click` — CLI framework (`kb` command)
- `python-frontmatter` — Parse/validate YAML frontmatter in wiki pages
- `networkx`, `pyvis` — Knowledge graph building and visualization
- `deepdiff` — Diff detection for drift checks and differential compilation
- `python-dotenv` — `.env` file loading

**Ingestion tools (active now):**
- `crawl4ai`, `firecrawl-py`, `trafilatura` — Web scraping → `raw/` ingestion
- `markitdown`, `PyMuPDF`, `python-docx`, `docling` — Document-to-markdown conversion
- `yt-dlp` — YouTube transcript extraction
- `arxiv` — arXiv paper fetching
- `feedparser` — RSS feed monitoring for source discovery
- `textstat` — Readability scoring for wiki pages during lint

**Phase 2+ (installed but not yet used):**
- `dspy` — Structured LLM pipelines for the ingest/compile cycle (Phase 3: Teacher-Student optimization)
- `ragas` — Quality evaluation for wiki accuracy (Phase 3: automated faithfulness scoring)
- `langchain`, `langgraph` — Agent orchestration (Phase 2: multi-agent workflows)
- `fastmcp` — Build MCP servers to expose wiki operations as tools (Phase 2/3)
- `obsidiantools` — Obsidian vault analysis (Phase 2: at 50+ wiki pages)
- `sqlite-vec`, `model2vec` — Optional local vector search (if wiki exceeds 800K words)
- `watchdog` — Filesystem monitoring for `raw/` auto-ingestion (Phase 2)

## Implementation Phases

Detailed architecture research is in `research/agent-architecture-research.md`. Key patterns to adopt per phase:

- **Phase 1 (Now):** Content-hash incremental compile, three index files, model tiering, structured lint output. Focus: get Ingest and Compile working end-to-end.
- **Phase 2 (50+ pages):** Multi-loop supervision for Lint, Actor-Critic compile (separate context for reviewer), query feedback loop, Self-Refine on Compile.
- **Phase 3 (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave (backward propagation of new knowledge through existing pages).

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only):
- **git-mcp** — Fetches documentation from GitHub repositories via [gitmcp.io](https://gitmcp.io/docs)
- **context7** — Fetches up-to-date library/framework documentation via `@upstash/context7-mcp`
- **fetch** — Fetches web pages and converts to markdown via `mcp-server-fetch` (official, Python-based via `uvx`)
- **memory** — Persistent knowledge graph (entities, relations, observations) via `@modelcontextprotocol/server-memory`. Stores in `.memory/memory.jsonl`. Useful for tracking wiki entity relationships across sessions
- **filesystem** — File operations (read, write, edit, search, directory tree) via `@modelcontextprotocol/server-filesystem`. Scoped to project root. Most useful for external agent pipelines
- **git** — Git operations (status, diff, log, commit, branch) via `mcp-server-git`. Useful for audit trails in Lint operations
- **arxiv** — Search arXiv papers, fetch abstracts, download PDFs via `arxiv-mcp-server`. Papers stored in `raw/papers/`. For Ingest pipeline
- **sqlite** — Structured metadata storage via `mcp-server-sqlite`. DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results — data awkward to track in frontmatter alone

**Planned (not yet configured):**
- **brave-search** — Web search via `@brave/brave-search-mcp-server`. Pending `BRAVE_API_KEY` activation. Meanwhile, use `fetch` MCP + `crawl4ai`/`trafilatura` CLI for web content, and Exa MCP (available via plugins) for neural search

## Philosophy

**Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.**
