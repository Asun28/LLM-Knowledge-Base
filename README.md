# 🌪️ LLM Wiki Flywheel

**Language / 语言：** **English** · [简体中文](README.zh-CN.md)

> **Compile, don't retrieve.** Drop a source in. Claude does the rest — extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. Markdown-first; optional hybrid retrieval. Pure markdown you own, browsable in Obsidian.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#development)
[![MCP Tools](https://img.shields.io/badge/MCP%20tools-28-blueviolet)](#claude-code-integration-mcp-server)
[![Version](https://img.shields.io/badge/version-v0.11.0-orange)](CHANGELOG.md)

Inspired by [Karpathy's LLM Knowledge Bases](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — then **fully automated**. Works natively inside Claude Code via 28 MCP tools — **no API key required**. Also runs on any local AI CLI tool (Ollama, Gemini CLI, OpenCode, Codex CLI, and more) via `KB_LLM_BACKEND`.

### 🎯 Why users pick this over RAG

- 🧠 **Structure first, optional vectors.** Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.
- ⚡ **Incremental by default.** SHA-256 change detection; only new/changed sources reprocessed.
- 🔗 **Retroactive linking.** Ingest a new topic → existing pages auto-gain `[[wikilinks]]` to it.
- 🧪 **Self-healing.** Bayesian trust scoring, contradiction detection, staleness flags, dead-link lint.
- 🦉 **Obsidian-native.** Open `wiki/` as a vault — free graph view, backlinks, hover preview.
- 🔌 **MCP-first.** 28 tools in Claude Code. Talk to your wiki: *"ingest this"*, *"what do we know about X?"*
- 📤 **Publishable.** One command emits `/llms.txt`, `/llms-full.txt`, `/graph.jsonld`, sitemap, per-page siblings — the Karpathy Tier-1 machine-consumable stack.

## Why Not RAG?

RAG retrieves chunks. This system **understands structure**.

| | RAG | This Project |
|---|---|---|
| Storage | Vector embeddings you can't read | Markdown pages you can browse in Obsidian |
| Knowledge | Chunks with no relationships | Entities, concepts, and wikilinks forming a graph |
| Quality | Hope the top-K chunks are relevant | BM25 + PageRank ranking with trust scores |
| Maintenance | Re-embed when sources change | Incremental compile — only changed sources reprocessed |
| Contradictions | Silently returns conflicting chunks | Lint detects contradictions across sources |
| Gaps | No way to know what's missing | Evolve analyzes coverage gaps and suggests new pages |

## What Makes This Different from [Karpathy's Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)?

Karpathy described a pattern where you manually ask an LLM to compile pages. This is a **fully automated system** — drop a file in `raw/`, run `kb compile`, and the entire pipeline runs without human intervention: extraction, page creation, cross-linking, index updates, and quality checks. Add Claude Code and you don't even need the CLI — just say "ingest this."

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
| No change detection | **Incremental compile** — SHA-256 hashes detect changes, only reprocesses what's new |
| No cross-linking | **Retroactive wikilink injection** — new topics auto-linked into existing pages |
| No quality checks | **Self-healing** — lint catches problems, trust scoring flags bad pages, contradiction detection |
| No gap awareness | **Evolve** — automatically identifies missing coverage and connection opportunities |
| External LLM calls | **MCP-native** — 28 tools inside Claude Code, no API key needed |
| Text-only | **Obsidian** — open `wiki/` as a vault, visual knowledge graph for free |

## The 30-Second Demo

```bash
# 1. Grab an article
trafilatura -u https://example.com/ai-article > raw/articles/ai-article.md

# 2. Ingest it — Claude extracts entities, concepts, key claims
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

**Human curates sources. Everything else is automated** — extraction, compilation, cross-linking, querying, health checks, and gap analysis all run without human intervention.

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

# OR — lean install (cycle 37, runtime-only, no extras):
#   pip install -r requirements-runtime.txt && pip install -e .
#
# OR — per-feature install (cycle 37, layered requirements files):
#   pip install -r requirements-runtime.txt -r requirements-hybrid.txt && pip install -e .
#   pip install -r requirements-runtime.txt -r requirements-augment.txt && pip install -e .
#   pip install -r requirements-runtime.txt -r requirements-formats.txt && pip install -e .
#   pip install -r requirements-runtime.txt -r requirements-eval.txt    && pip install -e .
#   pip install -r requirements-runtime.txt -r requirements-dev.txt     && pip install -e .
#
# OR — canonical extras (pyproject.toml, equivalent to layered requirements):
#   pip install -e .                # runtime only (no extras)
#   pip install -e '.[hybrid]'      # vector search via model2vec + sqlite-vec
#   pip install -e '.[augment]'     # kb_lint --augment fetcher (httpx + trafilatura)
#   pip install -e '.[formats]'     # kb_query --format=jupyter (nbformat)
#   pip install -e '.[eval]'        # ragas / litellm evaluation harness
#   pip install -e '.[dev]'         # pytest + ruff + pytest-httpx + build + twine
#
# Use requirements.txt for full reproducibility (frozen transitive pins);
# use requirements-runtime.txt + per-extra files when you want a leaner install
# without the full snapshot's dev tooling.
```

**API key:** Copy `.env.example` to `.env`. `ANTHROPIC_API_KEY` is optional for Claude Code/MCP mode and required only for direct API-backed CLI compile/query, MCP calls with `use_api=True`, and `kb_query --format=...` output adapters.

**Obsidian:** Open `wiki/` as a vault. Press `Ctrl+G` for the knowledge graph. See the **[full Obsidian guide](docs/guides/quickstart-obsidian.md)** ([HTML version](docs/guides/quickstart-obsidian.html)).

**Obsidian + remote storage (optional):** Install the [Remotely Save](https://github.com/remotely-save/remotely-save) community plugin (Apache 2.0) to sync your `wiki/` vault to S3, Azure Blob, OneDrive, or Dropbox. This lets non-technical users browse the compiled wiki on any device without touching the command line — your `kb` pipeline writes to the bucket, Remotely Save pulls it into Obsidian automatically.

**New here?** Browse the [`demo/`](demo/) folder — a small working wiki compiled from Karpathy's [X post](https://x.com/karpathy/status/2039805659525644595) and [LLM-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). It shows the full folder structure plus a real compiled output — summaries, entities, concepts, a comparison, and a cross-source synthesis — so you can see exactly what the pipeline produces before adding your own sources.

## Supported File Formats

Place source files under the matching `raw/` subdirectory, then run `kb ingest <file>` or `kb compile`.

| Format | Extensions | Notes |
|--------|------------|-------|
| Markdown | `.md` | Recommended for web clips, articles, notes, and converted documents |
| Plain text | `.txt` | Good for transcripts, notes, and simple exports |
| reStructuredText | `.rst` | Useful for Python/project documentation |
| Structured data | `.json`, `.yaml`, `.yml`, `.csv` | Useful for datasets, metadata, and exported records |

> **PDF files:** convert with [`markitdown`](https://github.com/microsoft/markitdown) or [`docling`](https://github.com/DS4SD/docling) first, then place the `.md` output in `raw/papers/`. Direct `.pdf` ingest is not supported (the binary content can't be parsed without a real PDF extractor — cycle 34 removed `.pdf` from the supported-extensions list to surface this earlier with a clear error).

For Office documents such as `.docx`, `.pptx`, or `.xlsx`, convert them to Markdown or CSV first, then place the converted file in `raw/`.

## Five Operations

| Operation | Command | What happens |
|-----------|---------|-------------|
| **Ingest** | `kb ingest <file>` | Extract entities, concepts, key claims → create wiki pages → inject wikilinks → update indexes |
| **Compile** | `kb compile` | Batch-ingest all new/changed sources (SHA-256 hash detection, crash-safe) |
| **Query** | `kb query "..."` | BM25 + PageRank search → synthesize answer with inline citations |
| **Lint** | `kb lint` | Dead links, orphan pages, staleness, stubs, frontmatter, source coverage, wikilink cycles, low-trust pages |
| **Evolve** | `kb evolve` | Coverage gaps, connection opportunities, missing page types, disconnected components |
| **Rebuild indexes** | `kb rebuild-indexes [--yes]` | Clean-slate wipe — deletes the hash manifest + vector DB + in-process LRU caches so the next `kb compile` re-ingests every source from scratch |

## Key Features

### Ingest Pipeline
- 10 source types: article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis
- Hash-based dedup — same content won't be ingested twice
- **Retroactive wikilink injection** — when you ingest a new topic, existing pages that mention it get auto-linked
- Cascade tracking — returns which existing pages might need review after the new ingest
- Short-source tiering — small sources (<1000 chars) defer entity creation to prevent stubs
- **Conversation capture** — `kb_capture` MCP tool atomizes chat / notes / session transcripts into typed knowledge items (decisions, discoveries, corrections, gotchas) with secret-scanner safety rails and a per-process rate limit

### Search & Query
- **BM25 ranking** with title boosting and document length normalization
- **PageRank blending** — well-connected pages rank higher
- Context truncated to 80K chars with intelligent page selection
- Inline citations: `[source: concepts/attention]` traces every claim

### Quality System
- **Bayesian trust scoring** — query feedback builds per-page trust. "Wrong" penalized 2x vs "incomplete"
- **Semantic lint** — deep fidelity checks (page vs source) and cross-page contradiction detection
- **Actor-Critic review** — structured 6-item review checklist with audit trail
- **Verdict trends** — weekly pass/fail/warning dashboard showing quality trajectory

### Knowledge Graph
- NetworkX-powered graph from wikilinks
- PageRank and betweenness centrality
- Mermaid diagram export (auto-prunes for large graphs)
- **Obsidian-compatible** — native graph view from `wiki/` vault

### Claude Code Integration (MCP Server)

28 tools that work natively in Claude Code. **No API key needed** — Claude Code is the default LLM.

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
| `kb_refine_list_stale` | List pending refine rows stale beyond a threshold (hours) — no mutation |
| `kb_refine_sweep` | Mark stale pending rows as failed or delete them, with audit trail |

</details>

## Model Tiering

Three Claude tiers balance cost and quality. Override via environment variables:

| Tier | Model | Override | Used For |
|------|-------|---------|----------|
| `scan` | Haiku 4.5 | `CLAUDE_SCAN_MODEL` | Index reads, link checks, diffs |
| `write` | Sonnet 4.6 | `CLAUDE_WRITE_MODEL` | Extraction, summaries, page writing |
| `orchestrate` | Opus 4.7 | `CLAUDE_ORCHESTRATE_MODEL` | Query synthesis, orchestration |

## Vibe Coding CLI Backends

Run the full KB pipeline against **any locally-installed AI CLI tool** — no Anthropic API key needed. Set `KB_LLM_BACKEND` and every `call_llm` / `call_llm_json` call routes through that tool's subprocess via stdin (shell injection-safe; stdout/stderr redacted before logging):

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

<details>
<summary><b>Project structure</b></summary>

```
llm-wiki-flywheel/
  raw/                     # Immutable source documents
    articles/papers/repos/videos/podcasts/books/datasets/conversations/assets/
  wiki/                    # LLM-generated wiki pages
    entities/concepts/comparisons/summaries/synthesis/
    index.md  _sources.md  _categories.md  log.md  contradictions.md
  templates/               # 10 YAML extraction schemas
  src/kb/                  # Python package (~6,200 lines)
    cli.py                 # Click CLI (6 commands)
    config.py              # Paths, model tiers, tuning constants
    mcp/                   # FastMCP server (28 tools)
    models/                # WikiPage, RawSource, frontmatter validation
    ingest/                # Pipeline + template-driven extractors
    compile/               # Incremental compiler + wikilink linker
    query/                 # BM25 + PageRank search + citations
    lint/                  # 8 checks + semantic lint + verdict trends
    evolve/                # Coverage analysis + connection discovery
    graph/                 # NetworkX graph + stats + Mermaid export
    feedback/              # Bayesian trust scoring
    review/                # Page-source pairing + refiner
    utils/                 # Hashing, LLM calls, text, I/O
  tests/                   # 2725 tests across 230 files
```

</details>

<details>
<summary><b>Development</b></summary>

```bash
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix

pip install -r requirements.txt && pip install -e .
python -m pytest                # 2985 passed, 10 skipped
ruff check src/ tests/ --fix    # Lint
ruff format src/ tests/         # Format
```

Python 3.12+. Ruff (line length 100, rules E/F/I/W/UP).

</details>

## Roadmap

- **Phase 4 (v0.10.0 shipped 2026-04-12):** Hybrid search with RRF fusion, 4-layer search dedup pipeline, evidence trail sections, stale truth flagging at query time, layered context assembly, raw-source fallback retrieval, auto-contradiction detection on ingest, multi-turn query rewriting. Post-release audit (unreleased) resolved all HIGH (23) + MEDIUM (~30) + LOW (~30) items.
- **Phase 4.11 (unreleased, 2026-04-14):** `kb_query --format={markdown|marp|html|chart|jupyter}` output adapters — synthesized answers saved as Markdown docs, Marp slide decks, self-contained HTML pages, matplotlib Python scripts (+ JSON data sidecar), or executable Jupyter notebooks. Files land at `outputs/{ts}-{slug}.{ext}` (gitignored) with provenance frontmatter. Addresses Karpathy Tier 1 #1.
- **Phase 5.0 (unreleased, 2026-04-15):** `kb lint --augment` — reactive gap-fill: lint detects a stub → propose authoritative URLs (Wikipedia, arxiv) → fetch with DNS-rebind-safe transport → ingest as `confidence: speculative`. Three-gate execution honors human curation: `propose → --execute → --auto-ingest`. Eligibility gates G1-G7 + scan-tier relevance check + post-ingest quality verdict + `[!gap]` callout on regression. Cross-process rate limiting: 10/run + 60/hour + 3/host/hour.
- **Phase 4.5 (unreleased, post-v0.10.0 audit, 2026-04-16 → 2026-04-22):** 22-cycle backlog blitz — 480+ acceptance criteria across 230 test files (+1548 tests: 1177 → 2725). Key deliverables: `kb.errors` exception taxonomy (`KBError` + 5 subclasses, `LLMError`/`CaptureError` reparented); slug-collision O_EXCL hardening with write-phase poison-unlink; 2 new MCP tools — `kb_refine_sweep` + `kb_refine_list_stale` (26 → 28 tools); `inject_wikilinks_batch` (N×M disk-read hot-path reduced to ~U+2M with ReDoS bounds); refine two-phase write with `attempt_id` correlation; ingest audit log (`.data/ingest_log.jsonl`, request_id correlation); per-page TOCTOU lock in linker; rotate-in-lock for wiki_log; Epistemic-Integrity 2.0 (`belief_state`, `authored_by`, `status` vocabularies); `kb publish` Tier-1 builders (5 formats: llms.txt, llms-full.txt, graph.jsonld, per-page siblings, sitemap); `kb_query(save_as=...)` synthesis persistence; duplicate-slug + inline-callout lint; manifest key consistency; 60+ security threats addressed across all cycles; 3-round PR review pattern for every batch ≥25 ACs; cycle 21: CLI subprocess backend for 8 alternative LLM providers (Ollama, Gemini CLI, OpenCode, Codex CLI, Kimi, QWEN, DeepSeek, ZAI) via `KB_LLM_BACKEND`; cycle 22: wiki-path ingest guard, universal extraction grounding clause, and `inspect.getsource` test replacement with a runtime LLM-call spy.
- **Phase 5 (deferred):** Inline claim-level confidence tags + EXTRACTED lint verification; claim-to-source BM25 grounding verification (retroactive hallucination detection — samples claims, verifies each against cited `raw/` source body, flags mismatches as `belief_state: uncertain`); multi-source confirmation gate (`belief_state: confirmed` requires ≥ 2 independent raw sources via `source_count` frontmatter tracking); URL-aware `kb_ingest` with 5-state adapter model; page status lifecycle (seed→developing→mature→evergreen); inline quality callout markers; autonomous research loop in evolve; chunk-level BM25 sub-page indexing; typed semantic relations on graph edges; interactive graph HTML viewer (vis.js); semantic edge inference (LLM-inferred implicit relationships); living overview page; actionable gap-fill source suggestions; two-phase compile pipeline; multi-hop retrieval; conversation→KB promotion; temporal claim tracking; BM25 + LLM reranking
- **Phase 6 (future):** DSPy optimization, RAGAS evaluation, Monte Carlo evidence sampling

<details>
<summary><b>Completed phases</b></summary>

- **v0.3.0:** 5 operations + graph + CLI + MCP server (12 tools)
- **v0.4.0:** Quality system — Bayesian trust, Actor-Critic review, semantic lint
- **v0.5.0:** Robustness — YAML injection protection, path canonicalization
- **v0.6.0:** DRY refactor — shared utilities, test fixtures. 180 tests
- **v0.7.0:** MCP server split, PageRank, entity enrichment, persistent verdicts. 234 tests
- **v0.8.0:** BM25 search engine. 252 tests
- **v0.9.0–v0.9.9:** Hardening, comprehensive audit, structured outputs, content growth. 564 tests
- **v0.9.10–v0.9.13:** Citation fixes, compile scan, BM25 dedup, 54-item backlog fix. 651 tests
- **v0.9.14:** Phase 3.95 — 38-item backlog remediation. 692 tests
- **v0.9.15:** Phase 3.96 — 153 fixes (4 CRITICAL, 31 HIGH, 54 MEDIUM, 64 LOW). 952 tests
- **v0.9.16:** Phase 3.97 — 62 fixes: atomic writes, MCP exception guards, slugify symbol mapping, CRLF fix, integer title coercion, contradiction detection improvements. 1033 tests
- **v0.10.0:** Phase 4 — hybrid search with RRF fusion (BM25 + vector via model2vec + sqlite-vec), 4-layer search dedup pipeline, evidence trail sections, stale truth flagging at query time, layered context assembly, raw-source fallback retrieval, auto-contradiction detection on ingest, multi-turn query rewriting. Post-release audit resolved all HIGH (23) + MEDIUM (~30) + LOW (~30) items. 1177 tests across 55 files
- **Phase 4.5 (unreleased, post-v0.10.0):** 22-cycle post-release audit + hardening (2026-04-16 → 2026-04-22). Exception taxonomy, slug-collision O_EXCL, ingest audit log, per-page TOCTOU lock, rotate-in-lock, batch wikilink injection, refine two-phase write, Epistemic-Integrity 2.0, `kb publish` 5 Tier-1 builders, `kb_query(save_as=...)`, duplicate-slug + inline-callout lint, manifest key consistency, 2 new MCP tools (28 total), 60+ security threats closed, CLI subprocess backends for 8 providers (cycle 21), wiki-path ingest guard and extraction grounding clause (cycle 22). 2725 tests across 230 files

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

This project is actively developed — **⭐ star the repo** to follow along. Each release ships meaningful new features (see [CHANGELOG.md](CHANGELOG.md)).

- **Found a bug?** Open an issue on [GitHub](https://github.com/Asun28/llm-wiki-flywheel/issues)
- **Have an idea?** Check the [Roadmap](#roadmap) first — if it's not there, open an issue to discuss
- **Want to follow along?** Star the repo and watch for releases — each phase ships meaningful new features

The codebase is intentionally readable: no magic frameworks, just Python + BM25 + NetworkX + FastMCP. If you've built knowledge systems, RAG pipelines, or LLM tooling before, the code should be familiar territory within 30 minutes.

> **Not accepting PRs yet** — the architecture is still evolving quickly and merging external changes is expensive. Issues, feedback, and ideas are the best way to contribute right now.

## License

[MIT License](LICENSE)
