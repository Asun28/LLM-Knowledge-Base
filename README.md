# LLM Knowledge Base

A personal, LLM-maintained knowledge wiki that **compiles** raw sources into structured, interlinked markdown — no RAG, no vector databases, just clean wiki pages built and maintained by Claude.

Inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## How It Works

```
raw/                    wiki/                         
  articles/               entities/                   
  papers/      Ingest      concepts/      Query       
  videos/    ---------> comparisons/ ----------> Answers
  repos/       Compile    summaries/     with citations
  books/                  synthesis/                   
  ...                     index.md                    
                          log.md                      
                                                      
              Lint -----> Health report               
              Evolve ---> Gap analysis                
```

**Human curates sources. LLM handles everything else** — extraction, compilation, linking, querying, maintenance, and gap analysis.

### Three-Layer Content Structure

| Layer | Path | Owner | Purpose |
|-------|------|-------|---------|
| **Raw** | `raw/` | Human | Immutable source documents (articles, papers, videos, repos, etc.) |
| **Wiki** | `wiki/` | LLM | Generated and maintained markdown pages with YAML frontmatter |
| **Research** | `research/` | Human | Analysis, project ideas, meta-research |

### Five Operations Cycle

| Operation | What it does |
|-----------|-------------|
| **Ingest** | Read a raw source, extract structured data via LLM, generate summary + entity + concept pages, update indexes |
| **Compile** | Scan all raw sources, detect changes via content hashes, batch-ingest new/modified sources |
| **Query** | Search wiki pages, synthesize answers with inline citations using Claude |
| **Lint** | Health checks: dead links, orphan pages, staleness, frontmatter validation, source coverage |
| **Evolve** | Gap analysis: under-linked concepts, missing page types, connection opportunities, new page suggestions |

## Quick Start

```bash
# Clone and set up
git clone https://github.com/Asun28/LLM-Knowledge-Base.git
cd LLM-Knowledge-Base

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Configure API key (optional — not needed with Claude Code Max)
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (only for kb ingest / kb query CLI commands)

# Verify installation
kb --version
```

## Usage

### Ingest a Source

Drop a markdown file into `raw/` and ingest it:

```bash
# Web article to markdown (pick one)
trafilatura -u https://example.com/article > raw/articles/article-name.md
crwl https://example.com/article -o markdown > raw/articles/article-name.md

# Ingest into the wiki
kb ingest raw/articles/article-name.md --type article
```

The ingest pipeline:
1. Reads the raw source
2. Calls Claude (Sonnet) to extract title, key claims, entities, concepts
3. Creates `wiki/summaries/article-name.md`
4. Creates/updates entity pages in `wiki/entities/`
5. Creates/updates concept pages in `wiki/concepts/`
6. Updates `wiki/index.md`, `wiki/_sources.md`, `wiki/log.md`

Source type is auto-detected from the `raw/` subdirectory, or specify with `--type`:
`article`, `paper`, `repo`, `video`, `podcast`, `book`, `dataset`, `conversation`

### Compile (Batch Ingest)

Process all new and changed sources at once:

```bash
kb compile              # Incremental (only new/changed sources)
kb compile --full       # Full recompile
```

Uses SHA-256 content hashes stored in `.data/hashes.json` to detect changes.

### Query

Ask questions and get answers with citations:

```bash
kb query "What is compile-not-retrieve?"
```

Searches wiki pages by keyword relevance, builds context, and calls Claude (Opus) to synthesize an answer with `[source: page_id]` citations.

### Lint

Run health checks:

```bash
kb lint
```

Checks for:
- Dead wikilinks (broken `[[references]]`)
- Orphan pages (no incoming links)
- Stale pages (not updated in 90+ days)
- Invalid frontmatter (missing required fields)
- Uncovered raw sources (not referenced by any wiki page)
- Low-trust pages flagged by query feedback

### Evolve

Analyze gaps and get improvement suggestions:

```bash
kb evolve
```

Reports:
- Coverage by page type (entities, concepts, comparisons, summaries, synthesis)
- Orphan concepts with no backlinks
- Unlinked pages that share terms (connection opportunities)
- Dead links that suggest new pages to create
- Disconnected graph components
- Coverage gaps from query feedback

### Claude Code Integration (MCP Server)

The knowledge base ships with a built-in [MCP server](https://modelcontextprotocol.io/) with **19 tools**. **Claude Code is the default LLM** — no API key needed. `kb_query` and `kb_ingest` use Claude Code for all intelligence; add `use_api=true` to call the Anthropic API instead.

```bash
# Start the MCP server standalone
kb mcp

# Or run as a Python module
python -m kb.mcp_server
```

**Setup:** Add to your `.mcp.json` (already configured in this repo):

```json
{
  "mcpServers": {
    "kb": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "kb.mcp_server"]
    }
  }
}
```

After restarting Claude Code, you get 19 tools:

#### Core Tools (Claude Code is the default LLM)

| Tool | Description |
|------|-------------|
| `kb_query` | Query the wiki. Returns context for Claude Code to answer. Add `use_api=true` for API synthesis. |
| `kb_ingest` | Ingest a source file. Pass `extraction_json` with your extraction; omit it to get the prompt first. Add `use_api=true` for API extraction. |
| `kb_ingest_content` | **One-shot**: provide raw content + extraction JSON; saves to `raw/` and creates all wiki pages. |
| `kb_save_source` | Save content to `raw/` without ingesting (ingest later with `kb_ingest`). |
| `kb_compile_scan` | List new/changed sources that need `kb_ingest`. |

#### Browse & Health Tools (always local)

| Tool | Description |
|------|-------------|
| `kb_search` | Keyword search across wiki pages |
| `kb_read_page` | Read a specific wiki page by ID |
| `kb_list_pages` | List all pages, optionally filtered by type |
| `kb_list_sources` | List all raw source files |
| `kb_stats` | Page counts, graph metrics, coverage info |
| `kb_lint` | Health checks (dead links, orphans, staleness, low-trust pages) |
| `kb_evolve` | Gap analysis and connection suggestions |

#### Quality Tools (Phase 2)

| Tool | Description |
|------|-------------|
| `kb_review_page` | Page + sources + checklist for quality review |
| `kb_refine_page` | Update page preserving frontmatter, with audit trail |
| `kb_lint_deep` | Source fidelity check (page vs raw source side-by-side) |
| `kb_lint_consistency` | Cross-page contradiction check |
| `kb_query_feedback` | Record query success/failure for trust scoring |
| `kb_reliability_map` | Page trust scores from feedback history |
| `kb_affected_pages` | Pages affected by a change (backlinks + shared sources) |

**Workflows:**

```
# Query (Claude Code answers directly)
kb_query("What is RAG?")  -> returns wiki context -> Claude Code synthesizes answer

# Ingest a file in raw/
kb_ingest("raw/articles/rag.md")                    -> returns extraction prompt
kb_ingest("raw/articles/rag.md", extraction_json=...) -> creates wiki pages

# Ingest a URL (one-shot)
1. Fetch content from URL
2. Extract title, entities, concepts
3. kb_ingest_content(content, "article-name", "article", extraction_json)

# Batch compile
kb_compile_scan()  -> lists sources -> kb_ingest each with extraction_json

# Quality review (Phase 2)
kb_review_page("concepts/rag")  -> review context -> kb_refine_page if issues
kb_lint_deep("concepts/rag")    -> fidelity check -> fix unsourced claims
kb_query_feedback(question, "useful", "concepts/rag")  -> builds trust scores
```

**Example prompts in Claude Code:**
> "Search my knowledge base for RAG" -> `kb_search`
> "What does my wiki say about transformers?" -> `kb_query`
> "Ingest this article into my wiki" -> `kb_ingest` or `kb_ingest_content`
> "Show me wiki health" -> `kb_lint`
> "What sources need processing?" -> `kb_compile_scan`
> "Review this wiki page for accuracy" -> `kb_review_page`

## Supported Source Types

| Type | Template | Capture Method |
|------|----------|----------------|
| Article | `templates/article.yaml` | `trafilatura -u URL` or `crwl URL -o markdown` |
| Paper | `templates/paper.yaml` | `markitdown file.pdf` or `docling file.pdf` |
| Video | `templates/video.yaml` | `yt-dlp --write-auto-sub --skip-download URL` |
| Repo | `templates/repo.yaml` | Manual markdown summary |
| Podcast | `templates/podcast.yaml` | Transcript markdown |
| Book | `templates/book.yaml` | Manual notes or `markitdown` |
| Dataset | `templates/dataset.yaml` | Schema documentation |
| Conversation | `templates/conversation.yaml` | Chat/interview transcript |

Each template defines extraction fields and wiki output mappings. The LLM uses these to consistently extract structured data from any source type. Source types are validated against this whitelist before processing.

## Wiki Page Format

Every wiki page uses YAML frontmatter for metadata:

```yaml
---
title: Retrieval Augmented Generation
source:
  - raw/articles/rag-overview.md
created: 2026-04-06
updated: 2026-04-06
type: concept
confidence: stated
---

# Retrieval Augmented Generation

RAG combines retrieval with generation...

## Key Claims

- Claim 1
- Claim 2

## Entities Mentioned

- [[entities/openai|OpenAI]]

## Concepts

- [[concepts/vector-search|Vector Search]]
```

**Page types:** `entity`, `concept`, `comparison`, `summary`, `synthesis`

**Confidence levels:** `stated` (directly from source), `inferred` (derived from multiple sources), `speculative` (LLM reasoning)

## Quality System (Phase 2)

The knowledge base includes a multi-layer quality system:

**Trust scoring** — Bayesian page trust based on query feedback. "Wrong" answers penalized 2x vs "incomplete". Pages below the trust threshold are automatically flagged during lint.

**Review workflow** — `kb_review_page` pairs wiki pages with their raw sources and a 6-item checklist (source fidelity, entity accuracy, wikilink validity, confidence match, no hallucination, title accuracy). Claude Code or a wiki-reviewer sub-agent evaluates and produces structured JSON reviews. Issues are fixed via `kb_refine_page` (max 2 rounds).

**Semantic lint** — Deep fidelity checks (`kb_lint_deep`) compare page claims against source content. Consistency checks (`kb_lint_consistency`) group related pages and detect contradictions.

**Affected page tracking** — After updating a page, `kb_affected_pages` identifies backlinks and shared-source pages that may need review.

## Model Tiering

The system uses three Claude model tiers to balance cost and quality:

| Tier | Model | Used For |
|------|-------|----------|
| `scan` | Claude Haiku 4.5 | Index reads, link checks, file diffs |
| `write` | Claude Sonnet 4.6 | Article writing, extraction, summaries |
| `orchestrate` | Claude Opus 4.6 | Query answering, orchestration, verification |

## Project Structure

```
LLM-Knowledge-Base/
  raw/                     # Immutable source documents
    articles/papers/repos/videos/podcasts/books/datasets/conversations/assets/
  wiki/                    # LLM-generated wiki pages
    entities/concepts/comparisons/summaries/synthesis/
    index.md               # Master catalog
    _sources.md            # Source traceability
    _categories.md         # Category tree
    log.md                 # Activity log
    contradictions.md      # Conflict tracker
  research/                # Human-authored analysis
  templates/               # 8 YAML extraction schemas
  src/kb/                  # Python package (~3,500 lines)
    cli.py                 # Click CLI (6 commands)
    config.py              # Paths, model tiers, tuning constants
    mcp_server.py          # FastMCP server (19 tools)
    models/                # WikiPage, RawSource, frontmatter validation
    ingest/                # Pipeline + extractors (template-driven)
    compile/               # Hash-based incremental compiler + linker
    query/                 # Keyword search engine + citation extraction
    lint/                  # 5 mechanical checks + semantic context builders
    evolve/                # Coverage analysis + connection discovery
    graph/                 # NetworkX graph builder + stats
    feedback/              # Bayesian trust scoring + reliability analysis
    review/                # Page-source pairing + frontmatter-preserving refiner
    utils/                 # Shared: hashing, markdown, LLM, text, wiki_log, pages
  tests/                   # 180 tests across 14 test files (2.4s)
```

## Development

```bash
# Activate venv (always use project .venv)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Install
pip install -r requirements.txt && pip install -e .

# Run tests
python -m pytest

# Lint & format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/
```

Python 3.12+. Ruff for linting (line length 100, rules E/F/I/W/UP).

## Roadmap

- **Phase 1 (complete, v0.3.0):** 5 operations + graph + CLI + MCP server (12 tools), hash-based incremental compile, model tiering
- **Phase 2 (complete, v0.4.0):** Quality system — feedback loop with Bayesian trust scoring, Actor-Critic review workflow, semantic lint (fidelity + consistency), page refiner with audit trail. 7 new MCP tools, wiki-reviewer agent
- **Phase 2.1 (complete, v0.5.0):** Robustness — weighted trust formula, path canonicalization, YAML injection protection, extraction validation, config-driven tuning
- **Phase 2.2 (complete, v0.6.0):** DRY refactor — shared utilities eliminated all code duplication, source type validation, source field normalization, consolidated test fixtures. 180 tests
- **Phase 3 (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave (backward propagation of new knowledge through existing pages). Research in `research/agent-architecture-research.md`

## License

Personal project. Not licensed for redistribution.
