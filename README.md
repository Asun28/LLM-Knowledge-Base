# 🌪️ LLM Wiki Flywheel

**Language / 语言：** **English** · [简体中文](README.zh-CN.md)

> **Compile, don't retrieve.** Drop a source in. Claude does the rest: extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. Markdown-first; optional hybrid retrieval. Pure markdown you own, browsable in Obsidian.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#development)
[![MCP Tools](https://img.shields.io/badge/MCP%20tools-28-blueviolet)](#claude-code-integration-mcp-server)
[![Version](https://img.shields.io/badge/version-v0.12.0-orange)](CHANGELOG.md)

Inspired by [Karpathy's LLM Knowledge Bases](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), then **fully automated**. Works natively inside Claude Code via 28 MCP tools, **no API key required**. Also runs on any local AI CLI tool (Ollama, Gemini CLI, OpenCode, Codex CLI, and more) via `KB_LLM_BACKEND`.

### 🎯 What you get

- 🧠 **Structure first, optional vectors.** Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.
- ⚡ **Incremental by default.** SHA-256 change detection; only new/changed sources reprocessed.
- 🔗 **Retroactive linking.** Ingest a new topic → existing pages auto-gain `[[wikilinks]]` to it.
- 🧪 **Self-healing.** Bayesian trust scoring, contradiction detection, staleness flags, dead-link lint.
- 🦉 **Obsidian-native.** Open `wiki/` as a vault for a free graph view, backlinks, and hover preview.
- 🔌 **MCP-first.** 28 tools in Claude Code. Talk to your wiki: *"ingest this"*, *"what do we know about X?"*
- 📤 **Publishable.** One command emits `/llms.txt`, `/llms-full.txt`, `/graph.jsonld`, sitemap, and per-page siblings: the Karpathy Tier-1 machine-consumable stack.

## Why Not RAG?

RAG retrieves chunks. This system **understands structure**.

| | RAG | This Project |
|---|---|---|
| Storage | Vector embeddings you can't read | Markdown pages you can browse in Obsidian |
| Knowledge | Chunks with no relationships | Entities, concepts, and wikilinks forming a graph |
| Quality | Hope the top-K chunks are relevant | Hybrid BM25 + vector ranking, PageRank blending, per-page trust scores |
| Maintenance | Re-embed when sources change | Incremental compile, only changed sources reprocessed |
| Contradictions | Silently returns conflicting chunks | Lint detects contradictions across sources |
| Gaps | No way to know what's missing | Evolve analyzes coverage gaps and suggests new pages |

## What Makes This Different from [Karpathy's Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)?

Karpathy described a pattern where you manually ask an LLM to compile pages. This is a **fully automated system**: drop a file in `raw/`, run `kb compile`, and the entire pipeline runs without human intervention: extraction, page creation, cross-linking, index updates, and quality checks. Add Claude Code and you don't even need the CLI, just say "ingest this."

```
                    ┌──────────────────────────────────────┐
                    │           The Full Cycle              │
                    │                                      │
    raw/            │   Ingest ──→ Compile ──→ Query       │        Obsidian
  articles/   ────→ │     │                      │         │ ────→  Graph View
  papers/           │     │    Evolve ←── Lint   │         │        Browse
  videos/           │     │      │          │    │         │        Search
  repos/            │     └──────┘←─────────┘←───┘         │
                    │        continuous feedback loop       │
                    └──────────────────────────────────────┘
```

| Karpathy's pattern (manual) | This project (fully automated) |
|---|---|
| Manually ask LLM to write pages | **One command** → extraction, page creation, linking, indexing all automatic |
| Flat list of pages | **Knowledge graph** with PageRank centrality and Mermaid export |
| No change detection | **Incremental compile**: SHA-256 hashes detect changes, only reprocesses what's new |
| No cross-linking | **Retroactive wikilink injection**: new topics auto-linked into existing pages |
| No quality checks | **Self-healing**: lint catches problems, trust scoring flags bad pages, contradiction detection |
| No gap awareness | **Evolve**: automatically identifies missing coverage and connection opportunities |
| External LLM calls | **MCP-native**: 28 tools inside Claude Code, no API key needed |
| Text-only | **Obsidian**: open `wiki/` as a vault, visual knowledge graph for free |

## The 30-Second Demo

```bash
# 1. Grab an article
trafilatura -u https://example.com/ai-article > raw/articles/ai-article.md

# 2. Ingest it. Claude extracts entities, concepts, key claims
kb ingest raw/articles/ai-article.md

# 3. Watch the wiki grow
#    wiki/summaries/ai-article.md        ← source summary
#    wiki/entities/openai.md             ← auto-created entity page
#    wiki/concepts/attention.md          ← auto-created concept page
#    + wikilinks injected into existing pages that mention these topics

# 4. Query across all your sources
kb query "How does attention relate to transformers?"
#    → synthesized answer with [source: page_id] citations

# 5. Check wiki health
kb lint     # dead links, orphan pages, stale content, contradictions
kb evolve   # what topics are missing? what should be connected?
```

Or just talk to Claude Code:

> "Ingest this article into my wiki"
> "What does my wiki say about transformers?"
> "Show me the knowledge graph"

## Architecture

![LLM Knowledge Base Architecture](docs/architecture/architecture-diagram.png)

[Detailed architecture diagram](docs/architecture/architecture-diagram-detailed.html)

**Human curates sources. Everything else is automated**: extraction, compilation, cross-linking, querying, health checks, and gap analysis all run without human intervention.

| Layer | Path | Owner | Purpose |
|-------|------|-------|---------|
| **Raw** | `raw/` | Human | Immutable source documents (articles, papers, videos, repos, etc.) |
| **Wiki** | `wiki/` | LLM | Generated and maintained markdown pages with YAML frontmatter |
| **Research** | `research/` | Human | Analysis, project ideas, meta-research |

## Quick Start

```bash
git clone https://github.com/Asun28/llm-wiki-flywheel.git
cd llm-wiki-flywheel

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

pip install -r requirements.txt && pip install -e .
kb --version

# OR install via pyproject extras (lean / per-feature):
#   pip install -e .                # runtime only (no extras)
#   pip install -e '.[hybrid]'      # vector search via model2vec + sqlite-vec
#   pip install -e '.[augment]'     # kb_lint --augment fetcher (httpx + trafilatura)
#   pip install -e '.[formats]'     # kb_query --format=jupyter (nbformat)
#   pip install -e '.[eval]'        # datasets / provider-eval scaffolding
#   pip install -e '.[dev]'         # pytest + ruff + pytest-httpx + build + twine
#
# Use requirements.txt for full reproducibility (frozen transitive pins).
```

### Non-clone install (`pip install`)

If you `pip install kb` without cloning the repo (e.g. as a library or MCP
server inside a separate project tree), set `KB_PROJECT_ROOT` to the directory
containing your wiki:

```bash
export KB_PROJECT_ROOT=/path/to/your/kb     # Unix
$env:KB_PROJECT_ROOT = "C:\path\to\your\kb"  # PowerShell
```

Without it, `kb.config` resolves data paths via a `cwd` → `pyproject.toml`
walk → installed-file-location heuristic (`config.py:get_project_root`),
which can land inside the venv `site-packages/` and silently write
`wiki/`/`raw/`/`.data/` there. Setting `KB_PROJECT_ROOT` makes the bootstrap
explicit and stable across `cd` operations. The env var is read at call time
(cycle 65 AC1), so a process-wide set is enough; no restart needed.

**API key:** Copy `.env.example` to `.env`. `ANTHROPIC_API_KEY` is optional for Claude Code/MCP mode and required only for direct API-backed CLI compile/query, MCP calls with `use_api=True`, and `kb_query --format=...` output adapters.

**Obsidian:** Open `wiki/` as a vault. Press `Ctrl+G` for the knowledge graph. See the **[full Obsidian guide](docs/guides/quickstart-obsidian.md)** ([HTML version](docs/guides/quickstart-obsidian.html)).

**Obsidian + remote storage (optional):** Install the [Remotely Save](https://github.com/remotely-save/remotely-save) community plugin (Apache 2.0) to sync your `wiki/` vault to S3, Azure Blob, OneDrive, or Dropbox. This lets non-technical users browse the compiled wiki on any device without touching the command line, your `kb` pipeline writes to the bucket, Remotely Save pulls it into Obsidian automatically.

**New here?** Browse the [`demo/`](demo/) folder, a small working wiki compiled from Karpathy's [X post](https://x.com/karpathy/status/2039805659525644595) and [LLM-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). It shows the full folder structure plus a real compiled output, summaries, entities, concepts, a comparison, and a cross-source synthesis, so you can see exactly what the pipeline produces before adding your own sources.

## Supported File Formats

Place source files under the matching `raw/` subdirectory, then run `kb ingest <file>` or `kb compile`.

| Format | Extensions | Notes |
|--------|------------|-------|
| Markdown | `.md` | Recommended for web clips, articles, notes, and converted documents |
| Plain text | `.txt` | Good for transcripts, notes, and simple exports |
| reStructuredText | `.rst` | Useful for Python/project documentation |
| Structured data | `.json`, `.yaml`, `.yml`, `.csv` | Useful for datasets, metadata, and exported records |

> **PDF files:** convert with [`markitdown`](https://github.com/microsoft/markitdown) or [`docling`](https://github.com/DS4SD/docling) first, then place the `.md` output in `raw/papers/`. Direct `.pdf` ingest is not supported (the binary content can't be parsed without a real PDF extractor, cycle 34 removed `.pdf` from the supported-extensions list to surface this earlier with a clear error).

For Office documents such as `.docx`, `.pptx`, or `.xlsx`, convert them to Markdown or CSV first, then place the converted file in `raw/`.

### Conversion Commands

KB ingest only supports `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.rst`, and `.csv`. Convert other formats before running `kb ingest`.

| Input | Convert command | KB output |
|-------|-----------------|-----------|
| Web article | `.\.venv\Scripts\python.exe -m trafilatura.cli -u URL > raw\articles\name.md` | `.md` |
| JS-heavy web page | `.\.venv\Scripts\python.exe -m crawl4ai.cli crawl URL -o markdown > raw\articles\name.md` | `.md` |
| PDF / DOCX / PPTX / XLSX | `.\.venv\Scripts\python.exe -m markitdown input.pdf -o raw\papers\name.md` | `.md` |
| Complex PDF / Office / image / VTT | `.\.venv\Scripts\python.exe -m docling.cli.main input.pdf --to md --output raw\papers` | `.md` |
| YouTube | `.\.venv\Scripts\python.exe -m yt_dlp --write-auto-sub --skip-download URL -o raw\videos\name`, then convert the `.vtt` file | `.md` / `.txt` |

For transcript files produced by `yt-dlp`, convert the generated `.vtt` before ingesting:

```powershell
.\.venv\Scripts\python.exe -m docling.cli.main raw\videos\video-name.en.vtt --from vtt --to md --output raw\videos
.\.venv\Scripts\python.exe -m kb.cli ingest raw\videos\video-name.en.md --type video
```

## Five Operations

| Operation | Command | What happens |
|-----------|---------|-------------|
| **Ingest** | `kb ingest <file>` | Extract entities, concepts, key claims → create wiki pages → inject wikilinks → update indexes |
| **Compile** | `kb compile` | Batch-ingest all new/changed sources (SHA-256 hash detection, crash-safe), then auto-publish |
| **Query** | `kb query "..."` | Hybrid BM25 + vector search with PageRank blending → synthesized answer with inline citations. `--format` writes it to `outputs/` |
| **Lint** | `kb lint` | Dead links, orphan pages, staleness, stubs, frontmatter, source coverage, wikilink cycles, duplicate slugs, low-trust pages. `--fix` repairs; `--augment` fills gaps from the web |
| **Evolve** | `kb evolve` | Coverage gaps, connection opportunities, missing page types, disconnected components |

Plus two maintenance commands:

| Command | What happens |
|---------|-------------|
| `kb publish [--format all]` | Emit `llms.txt`, `llms-full.txt`, `graph.jsonld`, `sitemap.xml`, and per-page siblings to `outputs/` (override with `--out-dir`) |
| `kb rebuild-indexes [--yes]` | Clean-slate wipe: deletes the hash manifest + vector DB + in-process LRU caches so the next `kb compile` re-ingests every source from scratch |

The CLI also mirrors most MCP tools (`kb search`, `kb stats`, `kb read-page`, `kb lint-deep`, `kb detect-drift`, …) for scripting without Claude Code.

## Key Features

### Ingest Pipeline
- 9 ingest source types: `article`, `paper`, `video`, `repo`, `podcast`, `book`, `dataset`, `conversation`, `capture` (`comparison` and `synthesis` are wiki page types, create them with `kb_create_page`)
- Hash-based dedup: same content won't be ingested twice
- **Retroactive wikilink injection**: when you ingest a new topic, existing pages that mention it get auto-linked
- **Evidence Trail**: every page keeps a reverse-chronological, sentinel-guarded record of which source contributed what, and when
- **Auto-contradiction detection**: a new source that conflicts with an existing page is flagged into `wiki/contradictions.md` at ingest time, not at query time
- Cascade tracking: returns which existing pages might need review after the new ingest
- Short-source tiering: small sources (<1000 chars) defer entity creation to prevent stubs
- **Conversation capture**: `kb_capture` MCP tool atomizes chat / notes / session transcripts into typed knowledge items (decisions, discoveries, corrections, gotchas) with secret-scanner safety rails and a per-process rate limit
- Structured audit log at `.data/ingest_log.jsonl` with `request_id` correlation across the whole pipeline

### Search & Query
- **Hybrid retrieval**: BM25 (title boosting + length normalization) fused with vector search via Reciprocal Rank Fusion; vectors are opt-in (`pip install -e '.[hybrid]'`) and degrade to BM25-only if unavailable
- **PageRank blending**: well-connected pages rank higher; `status: mature|evergreen` and human-authored pages get a mild ranking boost
- **4-layer dedup** so the same claim doesn't occupy three slots in your context window
- **Multi-turn query rewriting**: follow-up questions inherit context from the previous turn
- **Stale-truth flagging**: answers warn you when a cited page is older than its raw source
- **Raw-source fallback**: if no wiki page covers the question, the engine searches `raw/` directly instead of answering from nothing
- Context capped at 80K chars with intelligent page selection; inline citations (`[source: concepts/attention]`) trace every claim
- **Output adapters**: `kb query --format={markdown|marp|html|chart|jupyter}` writes the answer to `outputs/` as a doc, Marp deck, standalone HTML page, matplotlib script, or runnable notebook

### Quality System
- **Bayesian trust scoring**: query feedback builds per-page trust. "Wrong" penalized 2x vs "incomplete"
- **Semantic lint**: deep fidelity checks (page vs source) and cross-page contradiction detection
- **Actor-Critic review**: structured 6-item review checklist with audit trail
- **Verdict trends**: weekly pass/fail/warning dashboard showing quality trajectory
- **Epistemic integrity**: optional `belief_state` (confirmed / uncertain / contradicted / stale / retracted), `authored_by` (human / llm / hybrid), and `status` (seed → developing → mature → evergreen) frontmatter fields feed both ranking and publish filtering
- **Reactive gap-fill**: `kb lint --augment` spots a stub, proposes authoritative URLs, fetches them over a DNS-rebind-safe transport, and ingests as `confidence: speculative`. Three gates (`propose` → `--execute` → `--auto-ingest`) keep a human in the loop; rate-limited 10/run, 60/hour, 3/host/hour

### Knowledge Graph
- NetworkX-powered graph from wikilinks
- PageRank and betweenness centrality
- Mermaid diagram export (auto-prunes for large graphs)
- **Obsidian-compatible**: native graph view from `wiki/` vault

### Publish
`kb publish` emits the machine-consumable stack in one pass, and `kb compile` triggers it automatically on success:

| Artifact | What it is |
|---|---|
| `llms.txt` | Compact index of the wiki for LLM consumers |
| `llms-full.txt` | Full-text bundle of every publishable page |
| `graph.jsonld` | JSON-LD knowledge graph |
| `sitemap.xml` | Standard sitemap |
| per-page siblings | Sibling `.txt` next to each page for direct fetching |

Pages with `belief_state: retracted|contradicted` or `confidence: speculative` are skipped, so unverified content never lands in a published artifact.

`kb publish` writes to `outputs/` by default; the automatic post-compile run writes to `_publish/` alongside `wiki/` (kill-switch `KB_DISABLE_COMPILE_AUTO_PUBLISH=1`).

### Safety & Robustness
- **Atomic, locked writes**: every wiki page mutation runs under a reentrant per-page lock; the manifest, log, and verdict store use their own file locks
- **Path safety**: dual-anchor validation rejects traversal, Windows-illegal characters, and symlink escapes before any read or write
- **Prompt-injection fence**: all wiki and raw content is wrapped in a `<wiki_context>` boundary before it reaches an LLM, and scan-tier outputs are re-validated at the tier boundary before an orchestrate-tier consumer sees them
- **Crash-safe compile**: SHA-256 manifest + O_EXCL slug creation mean an interrupted run resumes instead of corrupting

### Claude Code Integration (MCP Server)

28 tools that work natively in Claude Code. **No API key needed**: Claude Code is the default LLM.

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

**Talk naturally:**

| What you want | What to say |
|---------------|------------|
| Ingest a file | "Ingest raw/articles/file.md into the wiki" |
| Ingest a URL | "Save this URL to my knowledge base: ..." |
| Ask a question | "What does my wiki say about transformers?" |
| Check health | "Run lint on my wiki" |
| Find gaps | "What topics are missing from my wiki?" |
| See the graph | "Show me the knowledge graph" |

<details>
<summary><b>All 28 MCP tools</b></summary>

#### Core

| Tool | Description |
|------|-------------|
| `kb_query` | Query the wiki. Returns context for Claude Code to answer. Add `use_api=true` for API synthesis. |
| `kb_ingest` | Ingest a source file. Pass `extraction_json` with your extraction; omit it to get the prompt first. |
| `kb_ingest_content` | One-shot: provide raw content + extraction JSON; saves to `raw/` and creates all wiki pages. |
| `kb_save_source` | Save content to `raw/` without ingesting. Errors if file exists unless `overwrite=true`. |
| `kb_capture` | Atomize up to 50KB of chat/notes/transcripts into typed `raw/captures/*.md` items via scan-tier LLM. Secret-scanner rejects API keys/tokens before any LLM call. |
| `kb_compile_scan` | List new/changed sources that need `kb_ingest`. |

#### Browse & Health

| Tool | Description |
|------|-------------|
| `kb_search` | BM25 + PageRank keyword search across wiki pages |
| `kb_read_page` | Read a specific wiki page by ID |
| `kb_list_pages` | List all pages, optionally filtered by type |
| `kb_list_sources` | List all raw source files |
| `kb_stats` | Page counts, graph metrics, coverage info |
| `kb_lint` | Health checks with auto-fix support |
| `kb_evolve` | Gap analysis and connection suggestions |
| `kb_detect_drift` | Find wiki pages stale due to raw source changes |
| `kb_compile` | Compile wiki from raw sources |
| `kb_graph_viz` | Export knowledge graph as Mermaid diagram |
| `kb_verdict_trends` | Weekly quality trends from verdict history |

#### Quality

| Tool | Description |
|------|-------------|
| `kb_review_page` | Page + sources + checklist for quality review |
| `kb_refine_page` | Update page preserving frontmatter, with audit trail |
| `kb_lint_deep` | Source fidelity check (page vs raw source) |
| `kb_lint_consistency` | Cross-page contradiction check |
| `kb_query_feedback` | Record query success/failure for trust scoring |
| `kb_reliability_map` | Page trust scores from feedback history |
| `kb_affected_pages` | Pages affected by a change (backlinks + shared sources) |
| `kb_save_lint_verdict` | Record lint/review verdict for audit trail |
| `kb_create_page` | Create comparison/synthesis/any wiki page directly |
| `kb_refine_list_stale` | List pending refine rows stale beyond a threshold (hours), no mutation |
| `kb_refine_sweep` | Mark stale pending rows as failed or delete them, with audit trail |

</details>

## Model Tiering

Three Claude tiers balance cost and quality. Override via environment variables:

| Tier | Model | Override | Used For |
|------|-------|---------|----------|
| `scan` | Haiku | `CLAUDE_SCAN_MODEL` | Index reads, link checks, diffs |
| `write` | Sonnet | `CLAUDE_WRITE_MODEL` | Extraction, summaries, page writing |
| `orchestrate` | Opus | `CLAUDE_ORCHESTRATE_MODEL` | Query synthesis, orchestration |

Each tier tracks the current model in its family. The exact pinned IDs live in [`src/kb/config.py`](src/kb/config.py) (`_DEFAULT_MODEL_TIERS`), which is the single source of truth; set the env var above to override a tier without touching code.

## Vibe Coding CLI Backends

Run the full KB pipeline against **any locally-installed AI CLI tool**: no Anthropic API key needed. Set `KB_LLM_BACKEND` and every `call_llm` / `call_llm_json` call routes through that tool's subprocess via stdin (shell injection-safe; stdout/stderr redacted before logging):

```bash
export KB_LLM_BACKEND=ollama    # pick one: ollama | gemini | opencode | codex | kimi | qwen | deepseek | zai
kb query "What is the compile-not-retrieve pattern?"
kb ingest raw/articles/my-notes.md
kb lint
```

| Backend | Install | Tier-default models |
|---------|---------|---------------------|
| **Ollama** | [ollama.com](https://ollama.com) | `llama3.2` / `qwen2.5-coder:7b` / `qwen2.5-coder:32b` |
| **Gemini CLI** | `npm install -g @google/gemini-cli` | _(CLI auto-selects)_ |
| **OpenCode** | `npm install -g opencode-ai` | _(CLI auto-selects)_ |
| **Codex CLI** | `npm install -g @openai/codex` | _(CLI auto-selects)_ |
| **Kimi** | `pip install kimi-cli` | _(CLI auto-selects)_ |
| **QWEN** | `pip install qwen-cli` | _(CLI auto-selects)_ |
| **DeepSeek** | `pip install deepseek-cli` | _(CLI auto-selects)_ |
| **ZAI** | `pip install zhipuai-cli` | _(CLI auto-selects)_ |

Override any tier's model with an env var:

```bash
export KB_CLI_MODEL_SCAN=llama3.2
export KB_CLI_MODEL_WRITE=qwen2.5-coder:7b
export KB_CLI_MODEL_ORCHESTRATE=qwen2.5-coder:32b
```

Unset `KB_LLM_BACKEND` (or set it to `anthropic`) to return to the default Claude path.

## Supported Sources

| Type | Capture Method |
|------|----------------|
| Article | `trafilatura -u URL` or `crwl URL -o markdown` |
| Paper | `markitdown file.pdf` or `docling file.pdf` |
| Video | `yt-dlp --write-auto-sub --skip-download URL` |
| Repo | Manual markdown summary |
| Podcast | Transcript markdown |
| Book | Manual notes or `markitdown` |
| Dataset | Schema documentation |
| Conversation | Chat/interview transcript |
| Capture | `kb_capture` MCP tool: atomizes a chat or session transcript into typed items |

Use the conversion commands above when the captured source is not already one of the supported text formats.

<details>
<summary><b>Project structure</b></summary>

```
llm-wiki-flywheel/
  raw/                     # Immutable source documents
    articles/papers/repos/videos/podcasts/books/datasets/conversations/captures/assets/
  wiki/                    # LLM-generated wiki pages
    entities/concepts/comparisons/summaries/synthesis/
    index.md  _sources.md  _categories.md  log.md  contradictions.md
  templates/               # 11 YAML schemas (9 ingest types + comparison/synthesis)
  src/kb/                  # Python package (~21,400 lines)
    cli.py                 # Click CLI (24 commands)
    config.py              # Paths, model tiers, tuning constants
    errors.py              # KBError taxonomy (ValidationError, StorageError, …)
    capture.py             # Chat/session transcript atomizer
    mcp/                   # FastMCP server (28 tools) + shared error boundary
    models/                # WikiPage, RawSource, frontmatter validation
    ingest/                # Pipeline + template-driven extractors + evidence trail
    compile/               # Incremental compiler, wikilink linker, publish builders
    query/                 # BM25 + vector hybrid, RRF, dedup, citations, formats/
    lint/                  # 8 checks + semantic lint + verdicts + augment/ gap-fill
    evolve/                # Coverage analysis + connection discovery
    graph/                 # NetworkX graph + stats + Mermaid export + cache
    feedback/              # Bayesian trust scoring
    review/                # Page-source pairing + refiner
    utils/                 # Hashing, LLM calls, page locks, path safety, I/O
  tests/                   # 3461 tests across 235 files
```

</details>

<details>
<summary><b>Development</b></summary>

```bash
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix

pip install -r requirements.txt && pip install -e .
python -m pytest                # 3421 passed, 24 skipped, 16 xfailed
ruff check src/ tests/ --fix    # Lint
ruff format src/ tests/         # Format
```

Python 3.12+. Ruff (line length 100, rules E/F/I/W/UP).

</details>

## Roadmap

### Shipped

| Phase | What landed |
|---|---|
| **4** (v0.10.0) | Hybrid search with RRF fusion, 4-layer dedup pipeline, evidence trails, stale-truth flagging at query time, auto-contradiction detection on ingest |
| **4.11** | `kb query --format={markdown\|marp\|html\|chart\|jupyter}`: answers exported as docs, Marp decks, standalone HTML, plot scripts, or notebooks |
| **5.0** | `kb lint --augment` reactive gap-fill: stub detected → propose authoritative URLs → safe fetch → ingest as `confidence: speculative`, behind a three-gate human approval flow |
| **4.5** | 22-cycle post-release audit: `kb.errors` taxonomy, `kb publish` Tier-1 builders, Epistemic-Integrity 2.0, 8 alternative CLI LLM backends, 60+ security threats closed |
| **Cycles 23-82** | Continued hardening: dual-anchor path safety, MCP error boundary, wiki-context boundary fence, tier-boundary verifier, reentrant per-page write lock |

Per-cycle detail lives in [`CHANGELOG.md`](CHANGELOG.md) and [`CHANGELOG-history.md`](CHANGELOG-history.md).

### Next: Phase 5 (deferred)

- **Grounding**: inline claim-level confidence tags + EXTRACTED lint; claim-to-source BM25 verification (retroactive hallucination detection); multi-source confirmation gate for `belief_state: confirmed`
- **Retrieval**: chunk-level BM25 sub-page indexing, multi-hop retrieval, BM25 + LLM reranking
- **Graph**: typed semantic relations, LLM-inferred implicit edges, interactive vis.js viewer, living overview page
- **Ingest**: URL-aware `kb_ingest` (5-state adapter), two-phase compile pipeline, conversation→KB promotion, temporal claim tracking, autonomous research loop in `evolve`

### Later: Phase 6

DSPy optimization, RAGAS evaluation, Monte Carlo evidence sampling.

<details>
<summary><b>Completed releases</b></summary>

| Version | Highlights | Tests |
|---|---|---|
| v0.3.0 | 5 operations + graph + CLI + MCP server (12 tools) |, |
| v0.4.0 | Quality system, Bayesian trust, Actor-Critic review, semantic lint |, |
| v0.5.0 | Robustness, YAML injection protection, path canonicalization |, |
| v0.6.0 | DRY refactor, shared utilities, test fixtures | 180 |
| v0.7.0 | MCP server split, PageRank, entity enrichment, persistent verdicts | 234 |
| v0.8.0 | BM25 search engine | 252 |
| v0.9.0–v0.9.9 | Hardening, comprehensive audit, structured outputs, content growth | 564 |
| v0.9.10–v0.9.13 | Citation fixes, compile scan, BM25 dedup, 54-item backlog fix | 651 |
| v0.9.14 | Phase 3.95, 38-item backlog remediation | 692 |
| v0.9.15 | Phase 3.96, 153 fixes (4 CRITICAL, 31 HIGH, 54 MEDIUM, 64 LOW) | 952 |
| v0.9.16 | Phase 3.97, 62 fixes: atomic writes, MCP exception guards, slugify symbol mapping, CRLF, integer title coercion | 1033 |
| v0.10.0 | Phase 4, hybrid search, 4-layer dedup, evidence trails, layered context, raw-source fallback, multi-turn rewriting | 1177 (55 files) |

</details>

## Special Thanks

| Project | What we learned |
|---------|----------------|
| [Karpathy's LLM Knowledge Bases](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | The original "compile, don't retrieve" pattern |
| [DocMason](https://github.com/JetXu-LLM/DocMason) | Validation gate, retrieve/trace loop, answer trace enforcement |
| [Graphify](https://github.com/safishamsi/graphify) | Community detection, per-claim confidence markers |
| [Sirchmunk](https://github.com/modelscope/sirchmunk) | Monte Carlo sampling, multi-turn query rewriting |
| [MemPalace](https://github.com/milla-jovovich/mempalace) | Layered context stack, temporal knowledge graph |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | Graph-based retrieval augmented generation |

<details>
<summary><b>More inspirations</b></summary>

| Project | What we learned |
|---------|----------------|
| [llm-wiki-compiler](https://github.com/ussumant/llm-wiki-compiler) | Two-phase compile pipeline |
| [rvk7895/llm-knowledge-bases](https://github.com/rvk7895/llm-knowledge-bases) | Claude Code plugin for Obsidian |
| [Ars Contexta](https://github.com/agenticnotetaking/arscontexta) | Knowledge system generation through conversation |
| [Remember.md](https://github.com/remember-md/remember) | Session knowledge extraction |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | Agent skills for Obsidian vaults |
| [lean-ctx](https://github.com/yvgude/lean-ctx) | Hybrid context optimization |
| [DSPy optimization patterns](https://github.com/KazKozDev/dspy-optimization-patterns) | Teacher-Student prompt tuning |
| [awesome-llm-knowledge-bases](https://github.com/SingggggYee/awesome-llm-knowledge-bases) | Curated tool list |
| [qmd](https://github.com/tobi/qmd) | Markdown-native querying |
| [Quartz](https://github.com/jackyzha0/quartz) | Static site generation from wiki |
| [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | Hot cache pattern, page status lifecycle, inline quality callouts, autonomous research loop |
| [llm-wiki-skill](https://github.com/sdyckjq-lab/llm-wiki-skill) | Inline claim-level confidence annotation, 5-state adapter model for URL-aware ingest |

</details>

## Contributing

This project is actively developed, **⭐ star the repo** to follow along. Each release ships meaningful new features (see [CHANGELOG.md](CHANGELOG.md)).

- **Found a bug?** Open an issue on [GitHub](https://github.com/Asun28/llm-wiki-flywheel/issues)
- **Have an idea?** Check the [Roadmap](#roadmap) first, if it's not there, open an issue to discuss
- **Want to follow along?** Star the repo and watch for releases, each phase ships meaningful new features

The codebase is intentionally readable: no magic frameworks, just Python + BM25 + NetworkX + FastMCP. If you've built knowledge systems, RAG pipelines, or LLM tooling before, the code should be familiar territory within 30 minutes.

> **Not accepting PRs yet**: the architecture is still evolving quickly and merging external changes is expensive. Issues, feedback, and ideas are the best way to contribute right now.

## License

[MIT License](LICENSE)
