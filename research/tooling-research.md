# Tooling Research: Deep Analysis

*Researched 2026-04-05. Based on deep search across GitHub repos, MCP ecosystem, and community consensus.*

---

## Patterns to Adopt from rvk7895/llm-knowledge-bases

Source: [rvk7895/llm-knowledge-bases](https://github.com/rvk7895/llm-knowledge-bases) — Claude Code plugin (SKILL.md files, zero Python). 4 stars, 14 commits, created 2026-04-02. Too immature to depend on, but rich in design patterns.

### 1. Hash-Based Incremental Compile

Track compiled-from hashes in `_index.md`. On each compile, scan `raw/`, diff against stored hashes, only process new/changed/deleted files. Simpler than maintaining a separate state file.

### 2. Three Index Files (not one)

| Index | Purpose |
|---|---|
| `_index.md` | Master article list with summaries and compiled-from hashes |
| `_sources.md` | Raw source → wiki article mapping (which sources produced which pages) |
| `_categories.md` | Auto-maintained category tree |

This is better than our planned single `wiki/index.md`. The source mapping is crucial for traceability during Lint.

### 3. Model Tiering Strategy

| Task | Model | Rationale |
|---|---|---|
| Scanning (index reads, link checks, file diffs) | Haiku | Mechanical, low-reasoning |
| Article writing and extraction | Sonnet | Good quality, cost-efficient |
| Orchestration, query answering, final verification | Opus | Highest reasoning needed |

Adopt this for cost efficiency — not everything needs Opus.

### 4. Evolve as a 5th Operation

Beyond Ingest/Compile/Query/Lint, add **Evolve**:
- Gap analysis — what topics lack coverage?
- Connection discovery — what concepts should be linked but aren't?
- Missing data — what raw sources would fill knowledge gaps?
- Interesting questions — what could be explored deeper?

User picks suggestions, LLM executes. This turns the wiki from passive to proactive.

### 5. Smart Filing Gate

When a query produces a good answer, don't automatically file it as a new wiki page. Only suggest filing when genuinely new knowledge was discovered (not just a restatement of existing pages). Prevents wiki bloat.

### Where We Do Better

| Feature | rvk7895 | Our Design |
|---|---|---|
| Epistemic confidence | No `confidence` field | `stated / inferred / speculative` per page |
| Audit trail | No log | Append-only `wiki/log.md` |
| Contradiction tracking | Lint catches but doesn't track | First-class contradiction registry |
| Python tooling | Pure prompt-only | Real code for hashing, link validation, index generation |
| Graph visualization | None | networkx + pyvis |

---

## MCP Server Ecosystem (April 2026)

### Installed (6 servers)

| Server | Package | Purpose |
|---|---|---|
| **git-mcp** | HTTP (gitmcp.io) | GitHub repo documentation |
| **context7** | `@upstash/context7-mcp` | Library/framework documentation |
| **fetch** | `mcp-server-fetch` (uvx) | Web page → markdown |
| **memory** | `@modelcontextprotocol/server-memory` | Persistent knowledge graph (entities, relations, observations) |
| **filesystem** | `@modelcontextprotocol/server-filesystem` | File operations for external agent pipelines |
| **git** | `mcp-server-git` (uvx) | Git operations for audit trails |

### Deferred: Obsidian MCP (revisit at 50+ wiki pages)

The ecosystem has matured. Best options when ready:

| Server | Stars | Status | Best For |
|---|---|---|---|
| **@bitbonsai/mcpvault** | 1,002 | Active (Mar 2026) | BM25 search, frontmatter-safe writes, tag management |
| **Epistates/turbovault** | 104 | Active, Rust-based | 44+ tools, link graph analysis, vault health checks |

Claude Code's built-in Read/Write/Edit/Grep/Glob covers 90% of what these offer. The one genuinely differentiated capability is **link graph analysis** (orphans, broken links, hubs, cycles) — only useful at scale.

### modelcontextprotocol/servers Repo Status

Reorganized from 20+ servers down to 7 core reference implementations. Many former servers archived to `modelcontextprotocol/servers-archived`. GitHub server moved to `github/github-mcp-server`.

---

## Publishing: Quartz

**[jackyzha0/quartz](https://github.com/jackyzha0/quartz)** — 11.7k stars, actively maintained.

The clear best choice for publishing `wiki/` as a website. Purpose-built for Obsidian-flavored markdown.

### Why Quartz

- Native `[[wikilinks]]` resolution (aliases, anchors, transclusions)
- Built-in interactive graph view (local + global)
- Built-in backlinks panel with popover previews
- Full YAML frontmatter parsing (our custom fields: title, source, type, confidence)
- Deploys to GitHub Pages with one workflow file

### Setup (when ready)

```bash
git clone https://github.com/jackyzha0/quartz.git
cd quartz && npm i
# Symlink wiki/ as content
rm -rf content && ln -s ../wiki content
npx quartz build --serve  # Local preview
```

### Why Not Alternatives

| | Wikilinks | Graph | Backlinks | Effort |
|---|---|---|---|---|
| **Quartz** | Native | Built-in | Built-in | Low |
| MkDocs | Plugin (fragile) | No | No | Low |
| Docusaurus | No | No | No | Medium |
| Hugo | Plugin (partial) | No | No | Medium |
| Obsidian Publish | Native | Built-in | Built-in | None ($8/mo) |

---

## Decisions: What We Deliberately Skipped

### Vector Databases — Skip

At 1M token context windows (standard across Claude, Gemini, GPT in 2026, no surcharge), a personal wiki of 100-1000 sources fits comfortably. The compiled wiki + index files + wikilinks + BM25 (already installed) covers all realistic query needs.

**Scaling path:** Hierarchical wikis (wiki-of-wikis), not vectors. Revisit if wiki exceeds ~800K words.

### spaCy / Standalone NLP — Skip

Claude API handles entity extraction, NER, and relationship extraction better than spaCy for this use case. `transformers` (already installed via docling) covers local NER if ever needed at batch scale. spaCy would add ~500MB for no benefit.

### llama_index — Skip

Against the compile-not-retrieve philosophy. The wiki IS the retrieval layer.

---

## Python Packages Installed (2026-04-05)

New additions to `requirements.txt` beyond the original set:

| Package | Purpose | Operation |
|---|---|---|
| `python-frontmatter` | Parse/validate YAML frontmatter | Compile, Lint |
| `deepdiff` | Diff detection for drift checks | Lint, Compile |
| `trafilatura` | Lightweight web article extraction | Ingest |
| `feedparser` | RSS feed monitoring | Ingest |
| `arxiv` | arXiv paper fetching | Ingest |
| `docling` | Complex PDF parsing (tables, figures) | Ingest |
| `ruff` | Python linter/formatter | Development |
| `pytest` | Testing framework | Development |
