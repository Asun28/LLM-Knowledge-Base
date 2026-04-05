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

# Configure API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

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

### Claude Code Integration (MCP Server)

The knowledge base ships with a built-in [MCP server](https://modelcontextprotocol.io/) so Claude Code can use it directly as a tool during conversations.

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

After restarting Claude Code, you get 13 tools in two modes:

#### Always Local (no API key)

| Tool | Description |
|------|-------------|
| `kb_search` | Keyword search across wiki pages |
| `kb_read_page` | Read a specific wiki page by ID |
| `kb_list_pages` | List all pages, optionally filtered by type |
| `kb_list_sources` | List all raw source files |
| `kb_stats` | Page counts, graph metrics, coverage info |
| `kb_lint` | Health checks (dead links, orphans, staleness) |
| `kb_evolve` | Gap analysis and connection suggestions |

#### With API Key (calls Anthropic API directly)

| Tool | Description |
|------|-------------|
| `kb_query` | LLM-powered Q&A with citations |
| `kb_ingest` | Ingest a raw source into the wiki |

#### Claude Code Native (no API key — Claude Code is the LLM)

| Tool | Description |
|------|-------------|
| `kb_query_context` | Returns wiki search results + full page content; Claude Code synthesizes the answer |
| `kb_ingest_prepare` | Reads source + template, returns extraction prompt for Claude Code to process |
| `kb_ingest_apply` | Takes Claude Code's extraction JSON and writes summary/entity/concept pages |
| `kb_compile_scan` | Lists new/changed sources; use with `kb_ingest_prepare`/`kb_ingest_apply` for each |

**Claude Code native workflow (no API key needed):**

```
# Query: ask a question
1. kb_query_context("What is RAG?")     → returns wiki context
2. Claude Code reads context             → synthesizes answer directly

# Ingest: add a source
1. kb_ingest_prepare("raw/articles/rag.md")  → returns extraction prompt
2. Claude Code extracts structured JSON       → from the prompt
3. kb_ingest_apply("raw/articles/rag.md", "article", '{"title":...}')  → writes pages

# Compile: batch process
1. kb_compile_scan()                     → lists sources needing ingestion
2. For each source: prepare → extract → apply
```

**Example in Claude Code:**
> "Search my knowledge base for articles about RAG" -> uses `kb_search`
> "What does my wiki say about transformer architectures?" -> uses `kb_query_context`
> "Ingest this article into my wiki" -> uses `kb_ingest_prepare` + `kb_ingest_apply`
> "Show me wiki health" -> uses `kb_lint`

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

Each template defines extraction fields and wiki output mappings. The LLM uses these to consistently extract structured data from any source type.

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

## Model Tiering

The system uses three Claude model tiers to balance cost and quality:

| Tier | Model | Used For |
|------|-------|----------|
| `scan` | Claude Haiku | Index reads, link checks, file diffs |
| `write` | Claude Sonnet | Article writing, extraction, summaries |
| `orchestrate` | Claude Opus | Query answering, orchestration, verification |

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
  src/kb/                  # Python package
    cli.py                 # Click CLI (6 commands)
    config.py              # Paths, model tiers, settings
    mcp_server.py          # FastMCP server for Claude Code (13 tools, 2 modes)
    models/                # WikiPage, RawSource, frontmatter
    ingest/                # Pipeline + extractors
    compile/               # Compiler + differ + linker
    query/                 # Engine + citations
    lint/                  # Checks + runner
    evolve/                # Gap analyzer
    graph/                 # NetworkX builder + pyvis visualizer
    utils/                 # Hashing, markdown, LLM wrapper
  tests/                   # 78 tests across 7 test files
```

## Development

```bash
# Run tests
python -m pytest -v

# Lint
ruff check src/ tests/
ruff check src/ tests/ --fix

# Format
ruff format src/ tests/
```

Python 3.12+. Ruff for linting (line length 100, rules E/F/I/W/UP).

## Roadmap

- **Phase 1 (complete):** All 5 operations + MCP server working end-to-end, 78 tests, CLI wired
- **Phase 2 (50+ pages):** Multi-loop supervision for Lint, Actor-Critic compile, query feedback loop
- **Phase 3 (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave (backward propagation of new knowledge through existing pages)

## License

Personal project. Not licensed for redistribution.
