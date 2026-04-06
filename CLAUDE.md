# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

**Phase 1 complete (v0.3.0).** All 5 operations, graph module, and MCP server are implemented, tested (78 tests), and wired to the CLI.

**Implemented and tested:**
- `kb.config` — paths, model tiers, page types, confidence levels
- `kb.models` — WikiPage, RawSource dataclasses, frontmatter validation
- `kb.utils` — hashing (SHA-256), markdown parsing (wikilinks, raw refs), LLM API wrapper (3-tier)
- `kb.ingest` — pipeline (read raw source → LLM extraction → generate wiki pages → update indexes), extractors (template loading, prompt building)
- `kb.compile` — compiler (hash-based incremental detection, batch orchestration), differ (unified diffs, dry-run), linker (wikilink resolution, backlinks)
- `kb.query` — engine (keyword search with title boosting, LLM synthesis), citations (extraction, formatting)
- `kb.lint` — checks (dead links, orphan pages, staleness, frontmatter validation, source coverage), runner (orchestrator, report formatting)
- `kb.evolve` — analyzer (coverage analysis, connection opportunities, new page suggestions, evolution report)
- `kb.graph` — builder (networkx DiGraph from wikilinks, statistics), visualize (pyvis HTML output)
- `kb.mcp_server` — FastMCP server exposing all KB operations as Claude Code tools
- CLI — all 6 commands fully wired: `ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`

**Phase 2 (50+ pages):** Multi-loop supervision for Lint, Actor-Critic compile, query feedback loop, Self-Refine on Compile. Detailed architecture research is in `research/agent-architecture-research.md`.

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
- **Compile**: LLM builds/updates interlinked wiki pages. Uses hash-based incremental detection — only processes new/changed sources. Proposes diffs, not full rewrites.
- **Query**: User asks questions. LLM searches wiki, synthesizes answers with inline citations to wiki pages and raw sources. Good answers become new wiki pages.
- **Lint**: Health check — orphan pages, dead links, staleness, circular reasoning, coverage gaps, frontmatter validation. Produces a report, does not silently fix.
- **Evolve**: Gap analysis — what topics lack coverage, what concepts should be linked, what raw sources would fill gaps. User picks suggestions, LLM executes.

### Python Package (`src/kb/`)

Entry point: `kb = "kb.cli:cli"` in `pyproject.toml`. Version in `src/kb/__init__.py`. MCP server entry: `python -m kb.mcp_server` or `kb mcp`.

All paths, model tiers, page types, and confidence levels are defined in `kb.config` — import from there, never hardcode. `PROJECT_ROOT` resolves from `config.py`'s location, so it works regardless of working directory.

**Key APIs:**
- `call_llm(prompt, tier="write")` — Anthropic API wrapper with model tiering. Tiers: `scan` (Haiku), `write` (Sonnet), `orchestrate` (Opus). Defined in `kb.utils.llm`.
- `content_hash(text)` — SHA-256, 16-char hex. For incremental compile change detection. In `kb.utils.hashing`.
- `extract_wikilinks(text)` / `extract_raw_refs(text)` — Regex extraction of `[[wikilinks]]` and `raw/...` references. In `kb.utils.markdown`.
- `load_page(path)` / `validate_frontmatter(post)` — Parse and validate wiki page YAML frontmatter. In `kb.models.frontmatter`. Required fields: `title`, `source`, `created`, `updated`, `type`, `confidence`.
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

8 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation). Each defines `extract:` fields and `wiki_outputs:` mapping to wiki subdirectories. All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages

78 tests across 7 test files covering models, ingest, compile, query, lint, evolve, and graph modules.

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

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

Key usage:
- **kb** — The knowledge base itself as an MCP server (`kb.mcp_server`, 15 tools). Start with `kb mcp` or `python -m kb.mcp_server`. This is the primary way Claude Code interacts with the wiki. Three modes:
  - **Claude Code Max** (RECOMMENDED, no API key — Claude Code IS the LLM):
    - `kb_ingest_content` — one-shot: provide content + extraction JSON, source saved and wiki pages created in one call.
    - `kb_save_source` — save fetched/pasted content to `raw/` for later ingestion.
    - `kb_query_context` — get wiki search context, synthesize the answer yourself.
    - `kb_ingest_prepare`/`kb_ingest_apply` — two-step for files already in `raw/`.
    - `kb_compile_scan` — find sources needing processing, loop prepare/apply.
  - **API mode** (needs `ANTHROPIC_API_KEY`): `kb_ingest`, `kb_query` — call the Anthropic API directly.
  - **Always local** (no API key): `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`, `kb_stats`, `kb_lint`, `kb_evolve`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation Phases

- **Phase 1 (Now):** Content-hash incremental compile, three index files, model tiering, structured lint output. Focus: get Ingest and Compile working end-to-end.
- **Phase 2 (50+ pages):** Multi-loop supervision for Lint, Actor-Critic compile, query feedback loop, Self-Refine on Compile.
- **Phase 3 (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave (backward propagation of new knowledge through existing pages).

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

## Automation

Auto-commit hooks are configured in `.claude/settings.local.json`:
- **Stop hook** — When Claude finishes a turn, if there are uncommitted changes and `pytest` passes, auto-commits with `auto: session checkpoint` message.
- **PostToolUse (Bash)** — After any Bash command containing `pytest` with "passed" in output, auto-commits with `auto: tests passed` message.

All tools are auto-approved for this project (permissions in `settings.local.json`).
