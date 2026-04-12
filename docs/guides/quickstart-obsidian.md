# Quickstart: LLM Knowledge Base with Obsidian

## What This System Does

Drop a source in. **Everything else is automatic.** Claude extracts entities and concepts, creates interlinked wiki pages, injects wikilinks into existing pages, tracks trust scores, detects contradictions, and self-maintains. Obsidian gives you a visual knowledge graph — for free.

Unlike [Karpathy's original pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) where you manually ask the LLM to compile pages, this system is **fully automated** — one command triggers the entire pipeline.

```
raw/articles/rag-overview.md     -->  wiki/summaries/rag-overview.md       (auto-created)
                                      wiki/entities/openai.md              (auto-created)
                                      wiki/concepts/retrieval-augmented-generation.md (auto-created)
                                      + wikilinks injected into existing pages (automatic)
                                      + trust scores, contradiction detection (automatic)
                                      + graph view in Obsidian              (instant)
```

## Prerequisites

- Python 3.12+
- [Obsidian](https://obsidian.md/) (free)
- Claude Code (for MCP integration) or an Anthropic API key (for CLI)

## Setup (5 minutes)

### 1. Install the knowledge base

```bash
git clone https://github.com/Asun28/llm-wiki-flywheel.git
cd llm-wiki-flywheel

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

pip install -r requirements.txt
pip install -e .

kb --version
```

### 2. Configure API key (skip if using Claude Code Max)

```bash
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=sk-ant-...
```

Claude Code Max users: the MCP tools use Claude Code as the LLM by default — no API key needed.

### 3. Open wiki/ as an Obsidian vault

1. Open Obsidian
2. Click **Open folder as vault**
3. Select the `wiki/` directory inside the project
4. Obsidian will index all existing wiki pages immediately

That's it. You now have a visual UI for your knowledge base.

## Your First Ingest

One trigger. Everything else is automatic.

### Option A: Via Claude Code (recommended)

In Claude Code, the KB MCP tools are available automatically:

```
> "Ingest this article about transformers into my wiki"

Claude Code automatically:
1. Reads the raw source
2. Extracts title, entities, concepts, key claims
3. Creates summary, entity, and concept pages with YAML frontmatter
4. Injects wikilinks into existing pages that mention the new topics
5. Updates index, sources mapping, and activity log
6. Returns affected pages for cascade review
--> Switch to Obsidian to see new pages in the graph
```

### Option B: Via CLI

```bash
# Grab an article
trafilatura -u https://example.com/article > raw/articles/my-article.md

# One command -- extraction, page creation, linking all automatic
kb ingest raw/articles/my-article.md --type article
```

### Option C: One-shot from URL (Claude Code)

```
> "Save this URL to my knowledge base: https://example.com/article"

Claude Code automatically:
1. Fetches the content
2. Saves to raw/ (with duplicate detection)
3. Extracts and creates all wiki pages in one step
```

After any ingest, switch to Obsidian and watch your graph grow.

## The Five Operations (Fully Automated Cycle)

The system runs a continuous feedback loop — each operation feeds into the next:

```
Ingest → Compile → Query → Lint → Evolve → (back to Ingest)
```

| Operation | How to run | What it automates | What to see in Obsidian |
|-----------|-----------|-------------------|-------------------------|
| **Ingest** | `kb ingest <file>` | Entity/concept extraction, page creation, wikilink injection, index updates | New pages in entities/, concepts/, summaries/ |
| **Compile** | `kb compile` | Hash-based change detection, batch ingest of new/modified sources | Multiple new pages from batch processing |
| **Query** | `kb query "..."` | BM25 + PageRank search, context assembly, cited answer synthesis | Answer with citations to wiki page IDs |
| **Lint** | `kb lint` | Dead links, orphans, staleness, stubs, contradictions, trust flags | Orphan nodes in graph (no connections) |
| **Evolve** | `kb evolve` | Coverage gap analysis, connection discovery, missing page suggestions | Suggested new pages and connections |

## Obsidian Tips

### Graph View

Press `Ctrl+G` (or `Cmd+G`) to open the graph view. You'll see:

- **Clusters** = related concepts linked by wikilinks
- **Orphan nodes** = pages with no connections (lint will flag these)
- **Hub nodes** = well-connected entities (high PageRank)

Filter by folder to focus on entities, concepts, or summaries.

### Recommended Settings

After opening the vault, configure these in Obsidian Settings:

| Setting | Where | Value |
|---------|-------|-------|
| Default new file location | Files & Links | `summaries/` |
| Use wikilinks | Files & Links | ON (already the default) |
| Detect all file extensions | Files & Links | OFF |
| Excluded files | Files & Links | `_sources.md`, `_categories.md` |

### Useful Community Plugins

These are optional but enhance the experience:

| Plugin | Why |
|--------|-----|
| **Dataview** | Query pages by frontmatter (e.g., show all pages with `confidence: speculative`) |
| **Graph Analysis** | Betweenness centrality, PageRank — mirrors `kb_graph_viz` |
| **Breadcrumbs** | Visual hierarchy from wikilinks |
| **Recent Files** | Quick access to newly ingested pages |

### Dataview Examples

Once you install Dataview, you can create query pages in your vault:

**Show all speculative claims:**
````markdown
```dataview
TABLE source, updated
FROM ""
WHERE confidence = "speculative"
SORT updated DESC
```
````

**Show pages by type:**
````markdown
```dataview
TABLE title, confidence, updated
FROM "entities"
SORT updated DESC
LIMIT 20
```
````

**Show pages from a specific source:**
````markdown
```dataview
TABLE title, type, confidence
FROM ""
WHERE contains(source, "raw/articles/rag-overview.md")
```
````

## Daily Workflow

```
Morning:
1. Find an interesting article/paper/video
2. Save to raw/  (trafilatura, crwl, yt-dlp, or manual)
3. Ingest via Claude Code or CLI
4. Open Obsidian, browse new pages, check graph

Weekly:
1. kb lint          --> fix dead links, stale pages
2. kb evolve        --> see what's missing, what to connect
3. Browse Obsidian graph for emerging clusters
```

## Wikilink Compatibility

The wiki uses `[[path/page-name|Display Name]]` format. Obsidian supports this natively — path-prefixed wikilinks work in both the editor and graph view.

If you create pages manually in Obsidian, use the same frontmatter format:

```yaml
---
title: "Your Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-09
updated: 2026-04-09
type: entity
confidence: stated
---
```

Then run `kb lint` to check your manual pages follow the same structure.

## Claude Code MCP Quick Reference

| What you want | What to say |
|---------------|------------|
| Ingest a file | "Ingest raw/articles/file.md into the wiki" |
| Ingest a URL | "Save this URL to my knowledge base: ..." |
| Ask a question | "What does my wiki say about transformers?" |
| Search pages | "Search my wiki for attention mechanisms" |
| Check health | "Run lint on my wiki" |
| Find gaps | "What topics are missing from my wiki?" |
| Review a page | "Review concepts/attention for accuracy" |
| See the graph | "Show me the knowledge graph" |
| Quality trends | "How is wiki quality trending?" |
| Find stale pages | "Which wiki pages have drifted from their sources?" |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Obsidian doesn't show pages | Make sure you opened `wiki/` as the vault, not the project root |
| Graph shows no connections | Pages need `[[wikilinks]]` — run `kb compile` to inject them |
| Ingest creates too many stub pages | Use `defer_small=True` for short sources (<1000 chars) |
| MCP tools not available | Check `.mcp.json` exists and restart Claude Code |
| API key errors | Set `ANTHROPIC_API_KEY` in `.env` (not needed for Claude Code Max) |
