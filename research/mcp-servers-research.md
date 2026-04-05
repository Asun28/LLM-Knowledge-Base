# MCP Servers Research for LLM Knowledge Base

*Researched 2026-04-06. Focused on MCP servers that would augment the Ingest/Compile/Query/Lint cycle.*

**Already configured:** git-mcp, context7, fetch, memory, filesystem, git

---

## 1. Obsidian Integration

### mcp-obsidian (MarkusPfundstein) -- RECOMMENDED
- **Package:** `npx -y mcp-obsidian` (npm: mcp-obsidian)
- **GitHub:** https://github.com/MarkusPfundstein/mcp-obsidian (3,207 stars)
- **Last pushed:** 2025-06-28 (not recently active)
- **License:** MIT
- **What it does:** Interacts with Obsidian vaults via the Obsidian Local REST API community plugin. Reads/writes notes, searches by content and tags, manages frontmatter, lists all files. Requires Obsidian desktop + the Local REST API plugin running.
- **KB relevance:** If we open the `wiki/` folder as an Obsidian vault, this gives the LLM structured access to notes, tags, and search through Obsidian's built-in index. Particularly useful for the Query operation since Obsidian's search understands wikilinks and tags natively.
- **Concern:** Requires Obsidian to be running. The project's filesystem MCP can already read/write files directly. Main value-add is Obsidian's search index and tag system.

### mcpvault (bitbonsai) -- ALTERNATIVE
- **Package:** Node-based, `npx mcpvault`
- **GitHub:** https://github.com/bitbonsai/mcpvault (1,002 stars)
- **Last pushed:** 2026-03-30 (actively maintained)
- **What it does:** Lightweight, safe read-only Obsidian vault access. Reads notes, searches, lists files. Does NOT require the Obsidian REST API plugin -- works directly on vault files.
- **KB relevance:** Safer alternative since it reads vault files directly without needing Obsidian running. Better fit for a CLI-first workflow like Claude Code. Read-only means it cannot corrupt wiki pages.
- **Concern:** Read-only. We need write access for the Compile operation.

### obsidian-mcp-server (cyanheads) -- MOST COMPREHENSIVE
- **GitHub:** https://github.com/cyanheads/obsidian-mcp-server (430 stars)
- **Last pushed:** recent (2026-04-04)
- **What it does:** Full-featured Obsidian MCP with read, write, search, tag management, frontmatter manipulation. Bridge to Obsidian Local REST API.
- **KB relevance:** Most feature-complete. Frontmatter tools are directly relevant since all wiki pages require YAML frontmatter. Search + tag + write = full Compile/Query coverage.

### zettelkasten-mcp (entanglr) -- INTERESTING APPROACH
- **GitHub:** https://github.com/entanglr/zettelkasten-mcp (146 stars)
- **What it does:** Implements the Zettelkasten note-taking methodology as an MCP server. Create atomic notes, link them, explore connections, synthesize knowledge.
- **KB relevance:** The knowledge base project IS essentially a Zettelkasten. Atomic notes, interlinking, synthesis -- these are exactly our wiki operations. Could provide structured note creation patterns.

**Verdict:** For this project, the filesystem MCP + direct file access is probably sufficient since we are not using Obsidian as an editor (we use it for viewing). If we later adopt Obsidian as the primary viewer, `mcp-obsidian` or `cyanheads/obsidian-mcp-server` would add search value. The zettelkasten-mcp is conceptually interesting but adds indirection.

---

## 2. Search/Retrieval

### knowledge-rag (lyonzin) -- STRONG CANDIDATE
- **GitHub:** https://github.com/lyonzin/knowledge-rag (42 stars)
- **Last pushed:** 2026-04-05 (very active)
- **What it does:** Local RAG system for Claude Code. Hybrid search (BM25 + semantic), cross-encoder reranking, markdown-aware chunking, 12 MCP tools. No external servers -- pure ONNX in-process.
- **KB relevance:** Directly solves the Query operation. Could index all of `wiki/` and `raw/` for semantic search. Markdown-aware chunking means it understands frontmatter and wikilinks. Zero external dependencies is ideal for local-first.
- **Install:** Python-based, likely `pip install` or clone.

### devrag (tomohiro-owada) -- LIGHTWEIGHT ALTERNATIVE
- **GitHub:** https://github.com/tomohiro-owada/devrag (45 stars)
- **Last pushed:** 2026-04-04 (active)
- **What it does:** Markdown vector search MCP server. Natural language search over markdown files using multilingual-e5-small embeddings.
- **KB relevance:** Simpler than knowledge-rag but might be sufficient. Designed specifically for markdown files. Multilingual embeddings could help with diverse source material.
- **Install:** Python-based.

### mnemonic (danielmarbach) -- INTERESTING CONCEPT
- **GitHub:** https://github.com/danielmarbach/mnemonic (18 stars)
- **What it does:** Local MCP memory server backed by plain markdown + JSON files, synced via git. No database. Project-scoped memory with semantic search.
- **KB relevance:** Aligned with our git-tracked, file-based philosophy. Memory stored as markdown means it integrates naturally with the wiki. However, overlaps significantly with the existing memory MCP.

**Verdict:** `knowledge-rag` is the strongest candidate here. Its hybrid search + markdown awareness + zero external dependencies make it ideal for a Query tool that searches across `wiki/` and `raw/`.

---

## 3. ArXiv/Academic

### arxiv-mcp-server (blazickjp) -- RECOMMENDED
- **Package:** `pip install arxiv-mcp-server` (PyPI, version 0.4.11)
- **GitHub:** https://github.com/blazickjp/arxiv-mcp-server (2,478 stars)
- **Last pushed:** 2026-04-03 (actively maintained)
- **What it does:** Search arXiv papers, fetch abstracts, download PDFs, get LaTeX sources. Designed for research workflows with Claude.
- **KB relevance:** Direct match for the Ingest operation. Search for papers on a topic, fetch them, save to `raw/papers/`. The project already has `arxiv` as a Python dependency -- this MCP server wraps it with Claude-friendly tools.
- **Install:** `pip install arxiv-mcp-server` then configure in `.mcp.json`

### arxiv-latex-mcp (takashiishida)
- **GitHub:** https://github.com/takashiishida/arxiv-latex-mcp (118 stars)
- **What it does:** Fetches and processes arXiv LaTeX sources for precise interpretation of mathematical expressions.
- **KB relevance:** Niche but valuable. If ingesting ML/AI papers, LaTeX source gives much better math representation than PDF-to-markdown conversion.

### Paper-Search-MCP (Dianel555)
- **GitHub:** https://github.com/Dianel555/paper-search-mcp-nodejs (135 stars)
- **What it does:** Multi-source academic paper search: Web of Science, arXiv, and more.
- **KB relevance:** Broader than arXiv-only. Useful if the knowledge base expands to non-arXiv academic sources.

**Verdict:** `arxiv-mcp-server` by blazickjp is the clear winner -- 2.5K stars, actively maintained, Python-based (fits our stack), and directly serves the Ingest pipeline for academic papers.

---

## 4. YouTube Transcript

### mcp-server-youtube-transcript (kimtaeyoon83) -- MOST POPULAR
- **Package:** `npx -y @kimtaeyoon83/mcp-server-youtube-transcript`
- **GitHub:** https://github.com/kimtaeyoon83/mcp-server-youtube-transcript (510 stars)
- **What it does:** Downloads YouTube video transcripts directly. Simple, single-purpose.
- **KB relevance:** Directly serves Ingest. Given a YouTube video URL, extract transcript and save to `raw/videos/`. The project already uses `yt-dlp` for this, but an MCP server makes it tool-callable from Claude.
- **Concern:** npm package last published 2024-11-29. Not recently updated.

### mcp-youtube-transcript (jkawamoto) -- BETTER MAINTAINED
- **GitHub:** https://github.com/jkawamoto/mcp-youtube-transcript (360 stars)
- **Last pushed:** 2026-04-05 (very active)
- **What it does:** Same core functionality -- retrieve YouTube transcripts via MCP.
- **KB relevance:** Same as above but more actively maintained.

### youtube-connector-mcp (ShellyDeng08)
- **GitHub:** https://github.com/ShellyDeng08/youtube-connector-mcp (72 stars)
- **What it does:** Full YouTube MCP: search videos, channels, playlists, AND transcripts.
- **KB relevance:** The search capability adds value -- find relevant videos on a topic, then extract their transcripts for ingestion. More than just transcript extraction.

**Verdict:** The project already has `yt-dlp` which Claude can invoke via Bash. An MCP server adds convenience but is lower priority. If adding one, `jkawamoto/mcp-youtube-transcript` for maintenance quality or `youtube-connector-mcp` for the search+transcript combo.

---

## 5. RSS/Feed Monitoring

### rss-mcp (veithly)
- **GitHub:** https://github.com/veithly/rss-mcp (31 stars)
- **Last pushed:** 2025-12-12
- **What it does:** TypeScript MCP server to fetch and parse RSS/Atom feeds, with special RSSHub support.
- **KB relevance:** Could automate source discovery. Monitor RSS feeds of ML blogs, arXiv categories, YouTube channels, and alert when new content is available for ingestion.

### mcp_rss (buhe)
- **GitHub:** https://github.com/buhe/mcp_rss (26 stars)
- **What it does:** MCP server for interacting with RSS feeds.

### feed-mcp (richardwooding)
- **GitHub:** https://github.com/richardwooding/feed-mcp (19 stars)
- **Last pushed:** 2026-03-31 (recent)
- **What it does:** RSS, Atom, and JSON Feed support.

**Verdict:** This space is immature. All options are low-star-count. The project already has `feedparser` as a Python dependency. Better to build a custom MCP server using `fastmcp` + `feedparser` than depend on any of these. This is a good candidate for a custom-built server (the project already has `fastmcp` as a dependency).

---

## 6. Knowledge Graph (Advanced)

### mcp-knowledge-graph (shaneholloman) -- RECOMMENDED UPGRADE
- **GitHub:** https://github.com/shaneholloman/mcp-knowledge-graph (838 stars)
- **Last pushed:** 2026-04-05 (actively maintained)
- **What it does:** Fork of the official memory server, focused on local development. Persistent memory through a local knowledge graph with enhanced entity/relation management.
- **KB relevance:** Drop-in upgrade for the existing `@modelcontextprotocol/server-memory`. Better local development experience. Could track wiki entity relationships more richly.

### atlas-mcp-server (cyanheads)
- **GitHub:** https://github.com/cyanheads/atlas-mcp-server (471 stars)
- **Last pushed:** 2026-04-05 (active)
- **What it does:** Neo4j-powered task management with three-tier architecture: Projects, Tasks, Knowledge. Includes deep research capabilities.
- **KB relevance:** Overkill for pure knowledge management. The Projects/Tasks layer is unnecessary. However, the Knowledge tier with Neo4j graph could be powerful for tracking entity relationships across wiki pages. Requires Neo4j (external dependency).

### context-portal (GreatScottyMac)
- **GitHub:** https://github.com/GreatScottyMac/context-portal (762 stars)
- **What it does:** Project-specific knowledge graph for AI assistants. RAG for context-aware development.
- **KB relevance:** Designed for code projects, not knowledge management. Conceptually similar but wrong domain.

### knowledge-base-server (willynikes2)
- **GitHub:** https://github.com/willynikes2/knowledge-base-server (131 stars)
- **What it does:** Persistent memory with SQLite FTS5, MCP server, Obsidian sync, and self-learning intelligence pipeline.
- **KB relevance:** Very closely aligned with this project's goals. SQLite FTS5 for full-text search + Obsidian sync + persistent memory. Worth deeper investigation.

**Verdict:** `mcp-knowledge-graph` is a safe incremental upgrade to the existing memory server. `knowledge-base-server` is the most aligned but needs more investigation. Neo4j-based options add too much infrastructure.

---

## 7. Markdown Processing

No dedicated MCP servers found specifically for markdown manipulation or link analysis. This is a gap in the ecosystem.

The closest options:
- **filesystem MCP** (already configured) handles read/write
- **knowledge-rag** (section 2) understands markdown structure
- **Obsidian MCPs** (section 1) understand wikilinks

**Verdict:** Build custom tooling using `fastmcp` + `python-frontmatter` (already a dependency). A custom MCP server could provide: wikilink extraction, frontmatter validation, broken link detection, orphan page finding -- all needed for the Lint operation.

---

## 8. Browser/Scraping (Enhanced)

### playwright-mcp (Microsoft) -- OFFICIAL, HIGH QUALITY
- **Package:** `npx @anthropic-ai/mcp-server-playwright` or `npx @playwright/mcp`
- **GitHub:** https://github.com/microsoft/playwright-mcp (30,297 stars)
- **What it does:** Official Playwright MCP server by Microsoft. Full browser automation: navigate, click, fill forms, take screenshots, extract content. Headless or headed mode.
- **KB relevance:** Already have Playwright installed for crawl4ai. This MCP server gives Claude direct browser control for complex scraping scenarios (JavaScript-heavy sites, login-required content, interactive pages).
- **Note:** Already available as a tool in the current environment (see deferred tools list).

### firecrawl-mcp-server (Firecrawl) -- RECOMMENDED
- **Package:** `npx -y firecrawl-mcp`
- **GitHub:** https://github.com/firecrawl/firecrawl-mcp-server (5,949 stars)
- **What it does:** Official Firecrawl MCP. Web scraping, crawling, and search. Converts pages to clean markdown. Can crawl entire sites, extract structured data.
- **KB relevance:** Directly serves Ingest. Firecrawl produces cleaner markdown than raw Playwright scraping. Site crawling is useful for ingesting entire documentation sites. The project already has `firecrawl-py` as a dependency.
- **Concern:** Firecrawl is a paid service (free tier exists). The project already has `crawl4ai` and `trafilatura` for free alternatives.

### fetcher-mcp (jae-jae)
- **GitHub:** https://github.com/jae-jae/fetcher-mcp (1,022 stars)
- **What it does:** Fetch web page content using Playwright headless browser. Simpler than full Playwright MCP.
- **KB relevance:** Lighter-weight alternative to Microsoft Playwright MCP when you just need page content, not full browser automation.

**Verdict:** Microsoft Playwright MCP is already available. For enhanced scraping, `firecrawl-mcp-server` adds site crawling and cleaner markdown extraction, but requires API key. The existing `fetch` MCP + `crawl4ai`/`trafilatura` CLI tools cover most needs.

---

## 9. Neural Search (Exa/Tavily/Brave)

### exa-mcp-server (Exa Labs) -- RECOMMENDED FOR RESEARCH
- **Package:** `npx -y exa-mcp-server` (npm: exa-mcp-server v3.2.0)
- **GitHub:** https://github.com/exa-labs/exa-mcp-server (4,152 stars)
- **Last pushed:** 2026-04-03 (active)
- **What it does:** Neural web search + live crawling via Exa. Searches web, finds academic papers, people, companies. Returns clean content. Configurable tool selection.
- **KB relevance:** Exa's neural search is specifically good at finding research papers, technical blog posts, and niche content -- exactly the sources this knowledge base needs. The `web_search_exa` and `crawling_exa` tools are powerful for the Ingest discovery phase.
- **Requires:** Exa API key (free tier: 1,000 searches/month).
- **Note:** Already available as a tool in the current environment.

### tavily-mcp (Tavily AI) -- RECOMMENDED FOR DEEP RESEARCH
- **GitHub:** https://github.com/tavily-ai/tavily-mcp (1,639 stars)
- **Last pushed:** 2026-04-05 (very active)
- **What it does:** Production-ready MCP with real-time search, content extraction, site mapping, and crawling.
- **KB relevance:** Tavily is optimized for AI-agent research workflows. Its extract tool pulls clean content from URLs. Site mapping discovers all pages on a domain. Strong for systematic ingestion of a topic.
- **Requires:** Tavily API key.

### brave-search-mcp-server (Brave) -- RECOMMENDED, FREE
- **Package:** `npx -y @brave/brave-search-mcp-server` (npm v2.0.75)
- **GitHub:** https://github.com/brave/brave-search-mcp-server
- **What it does:** Official Brave Search MCP. Web results, images, videos, rich results, AI summaries.
- **KB relevance:** Free-tier web search (2,000 queries/month with API key). Good general-purpose search for finding sources to ingest. Less specialized than Exa for academic content but broader coverage and free.
- **Requires:** Brave Search API key (free tier available).
- **Note:** The older `@modelcontextprotocol/server-brave-search` is DEPRECATED. Use `@brave/brave-search-mcp-server`.

**Verdict:** All three are valuable. Priority order for this project:
1. **Exa** -- best for academic/research content discovery (already available in env)
2. **Brave Search** -- free, broad web search for general source discovery
3. **Tavily** -- if budget allows, excellent for deep research workflows

---

## 10. Database (SQLite)

### mcp-server-sqlite (Official Anthropic) -- RECOMMENDED
- **Package:** `pip install mcp-server-sqlite` (PyPI, version 2025.4.25) or `uvx mcp-server-sqlite`
- **Part of:** Official Model Context Protocol reference servers
- **What it does:** SQLite database operations via MCP. Create tables, insert/query data, run SQL. Built on Python's sqlite3.
- **KB relevance:** Structured metadata storage for the knowledge base. Could store: page metadata (title, sources, created/updated dates), wikilink graph edges, ingestion history, lint results, search indices. Complements the file-based wiki with queryable structured data.
- **Install:** `uvx mcp-server-sqlite --db-path wiki/metadata.db`

### mcp-server-sqlite-npx (johnnyoshika) -- NODE ALTERNATIVE
- **Package:** `npx -y mcp-server-sqlite-npx`
- **What it does:** Same concept, Node.js implementation using better-sqlite3.
- **KB relevance:** Same as above. Choose based on stack preference (Python vs Node).

### mcp-alchemy (runekaagaard)
- **GitHub:** https://github.com/runekaagaard/mcp-alchemy (400 stars)
- **What it does:** SQLAlchemy-based MCP server supporting SQLite, PostgreSQL, MySQL, Oracle, MS-SQL.
- **KB relevance:** More powerful than the basic SQLite server. If the knowledge base ever needs a more complex database, this scales. But overkill for now.

### genai-toolbox (Google) -- ENTERPRISE SCALE
- **GitHub:** https://github.com/googleapis/genai-toolbox (13,775 stars)
- **What it does:** Open-source MCP server for databases. Supports many backends.
- **KB relevance:** Enterprise-grade, way too heavy for a personal knowledge base.

**Verdict:** The official `mcp-server-sqlite` is the right choice. Python-based, maintained by Anthropic, minimal. Use it to store structured metadata that is awkward to track in markdown frontmatter alone (e.g., wikilink graph, ingestion history, lint reports).

---

## Priority Recommendations

### Tier 1: Add Now (high value, low friction)
| Server | Category | Install | Why |
|---|---|---|---|
| `arxiv-mcp-server` | Academic | `pip install arxiv-mcp-server` | Direct Ingest support for papers |
| `mcp-server-sqlite` | Database | `pip install mcp-server-sqlite` | Structured metadata for Lint/Query |
| `@brave/brave-search-mcp-server` | Search | `npx @brave/brave-search-mcp-server` | Free web search for source discovery |

### Tier 2: Add When Needed (good value, some setup)
| Server | Category | Install | Why |
|---|---|---|---|
| `knowledge-rag` | Local Search | Clone + setup | Semantic search over wiki/ and raw/ |
| Exa MCP | Neural Search | Already in env | Research-grade content discovery |
| `@playwright/mcp` | Browser | Already in env | Complex scraping for Ingest |

### Tier 3: Build Custom (gap in ecosystem)
| Tool | Category | Stack | Why |
|---|---|---|---|
| RSS monitor | Feed monitoring | `fastmcp` + `feedparser` | No good MCP exists; we have the deps |
| Markdown lint tools | Markdown processing | `fastmcp` + `python-frontmatter` | Wikilink validation, orphan detection |
| Wiki compiler | Core | `fastmcp` + `anthropic` | The Compile operation itself as MCP tools |

### Tier 4: Revisit Later
| Server | Category | Why wait |
|---|---|---|
| Obsidian MCPs | Obsidian | Only needed if Obsidian becomes primary viewer |
| `mcp-knowledge-graph` | Graph | Upgrade to existing memory server; wait for clear need |
| YouTube transcript MCPs | YouTube | `yt-dlp` via Bash is sufficient |
| Tavily MCP | Search | Paid; Exa + Brave cover the need |

---

## Configuration Sketch

For `.mcp.json` additions (Tier 1 servers):

```json
{
  "mcpServers": {
    "arxiv": {
      "command": "uvx",
      "args": ["arxiv-mcp-server"]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "wiki/metadata.db"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@brave/brave-search-mcp-server"],
      "env": {
        "BRAVE_API_KEY": "<key>"
      }
    }
  }
}
```

---

## Sources

All data gathered 2026-04-06 via GitHub API, npm registry, and PyPI. Star counts and last-pushed dates are point-in-time snapshots.
