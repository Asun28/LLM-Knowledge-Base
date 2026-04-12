# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

**Phase 3.97 complete (v0.9.16).** 1033 tests, 25 MCP tools, 12 modules. Phase 1 core (5 operations + graph + CLI) plus Phase 2 quality system (feedback, review, semantic lint) plus v0.5.0 fixes plus v0.6.0 DRY refactor plus v0.7.0 S+++ upgrade (MCP server split into package, graph PageRank/centrality, entity enrichment on multi-source ingestion, persistent lint verdicts, case-insensitive wikilinks, trust threshold fix, template hash change detection, comparison/synthesis templates, 2 new MCP tools). Plus v0.8.0 BM25 search engine (replaces bag-of-words keyword matching with BM25 ranking — term frequency saturation, inverse document frequency, document length normalization). Plus v0.9.0 hardening release (path traversal protection, citation regex fix, slug collision tracking, JSON fence hardening, MCP error handling, max_results bounds, MCP Phase 2 instructions).

**Phase 1 modules:** `kb.config`, `kb.models`, `kb.utils`, `kb.ingest`, `kb.compile`, `kb.query`, `kb.lint`, `kb.evolve`, `kb.graph`, `kb.mcp_server`, CLI (6 commands: `ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`). **MCP server split into `kb.mcp` package** (app, core, browse, health, quality).

**Phase 2 modules:**
- `kb.feedback` — query feedback store (weighted Bayesian trust scoring — "wrong" penalized 2x vs "incomplete"), reliability analysis (flagged pages, coverage gaps)
- `kb.review` — page-source pairing, review context/checklist builder, page refiner (frontmatter-preserving updates with audit trail)
- `kb.lint.semantic` — fidelity, consistency, completeness context builders for LLM-powered evaluation
- `.claude/agents/wiki-reviewer.md` — Actor-Critic reviewer agent definition
- `kb.lint.verdicts` — persistent lint/review verdict storage (pass/fail/warning with audit trail)

**Phase 3+ (200+ pages):** DSPy Teacher-Student optimization, RAGAS evaluation, Reweave. Research in `research/agent-architecture-research.md`.

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
- `query_wiki(question, wiki_dir=None, max_results=10)` — In `kb.query.engine`. Returns dict with `answer` (str), `citations` (list[dict] with keys `type` ('wiki'|'raw'), `path` (str), `context` (str)), `source_pages` (list[str] page IDs retrieved), `context_pages` (list[str] page IDs in LLM context). `context_pages` is empty list on no-match.
- `refine_page(page_id, content, notes)` — In `kb.review.refiner`. Uses regex-based frontmatter split (not YAML parser), rejects content that looks like a frontmatter block (`---\nkey: val\n---`) to prevent corruption.

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
| `orchestrate` | `claude-opus-4-6` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

### Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (4 subdirs) for Phase 2 tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

1033 tests across 43 test files — run `python -m pytest -v` to list all. New tests per phase go in versioned files (e.g., `test_v0916_task01.py`). Use the `tmp_wiki`/`tmp_project` fixtures for any test that writes files — never write to the real `wiki/` or `raw/` in tests.

### Error Handling Conventions

- **MCP tools**: Return `"Error: ..."` strings on failure — never raise exceptions to the MCP client. Page IDs validated via `_validate_page_id()` (rejects path traversal, verifies path within WIKI_DIR).
- **LLM calls**: Shared retry logic in `_make_api_call()` — 3 attempts with exponential backoff on rate limits/overload/timeout. `LLMError` on exhaustion. `call_llm_json()` uses forced tool_use for guaranteed structured JSON (no fence-stripping needed).
- **Page loading loops**: Catch specific exceptions (not broad `Exception`) and skip with warning — never abort a full scan for one bad file.
- **JSON stores**: All use `atomic_json_write()` (temp file + rename). Capped at 10,000 entries each (feedback, verdicts).
- **Ingest limits**: `MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50` — prevents runaway page creation from hallucinated lists.
- **Path traversal**: Validated at MCP boundary (`_validate_page_id`, ingest path check), at library level (`refine_page`, `pair_page_with_sources`), and in reference extraction. `extract_citations()` and `extract_raw_refs()` reject `..` and leading `/`.

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
```

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

Key usage:
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 25 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question)` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction. Output includes `affected_pages` (cascade review list) and `wikilinks_injected` (pages updated with retroactive links). Shows "Duplicate content detected" with hash if source was already ingested.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename, overwrite=false)` — save content to `raw/` for later ingestion. Returns error if file already exists unless `overwrite=true`.
  - `kb_compile_scan()` — find changed sources, then `kb_ingest` each.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint` (includes flagged pages + stub detection, supports `--fix`), `kb_evolve` (includes coverage gaps + stub enrichment suggestions), `kb_detect_drift` (finds wiki pages stale due to raw source changes), `kb_graph_viz` (Mermaid graph export with auto-pruning), `kb_verdict_trends` (weekly quality dashboard).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation History

See `CHANGELOG.md` for the full phase history (v0.3.0 → v0.9.16). Format: [Keep a Changelog](https://keepachangelog.com/) with Added/Changed/Fixed/Removed categories per version.

**Current:** Phase 3.97 (v0.9.16) — 1033 tests, 25 MCP tools, 12 modules. Plus v0.9.16 hardening release (4 remaining non-atomic writes, MCP exception guards, slugify symbol-to-word mapping, CRLF line ending fix, integer title coercion, date validation, citation type override, feedback null-type guard, code block masking in dead-link fixer).

**Known issues:** See `BACKLOG.md` for active backlog items. Format guide is in the HTML comment at the top of that file. Severity levels: CRITICAL (blocks release), HIGH (silent wrong results / security), MEDIUM (quality gaps / missing coverage), LOW (style/naming). Items grouped by severity then by module area. Resolved items are deleted (fix recorded in CHANGELOG.md); resolved phases collapse to a one-liner under "Resolved Phases".

**Phase 4 next (focused — 5 features):** Layered context assembly (replace naive 80K truncation with tiered loading: summaries first → full pages on demand — inspired by MemPalace's 4-layer context stack), raw-source fallback retrieval (search `raw/` directly alongside `wiki/` during queries for verbatim context when summaries lose nuance), multi-turn query rewriting (use conversation context to rewrite follow-up queries before searching — one LLM call to expand pronouns/references into standalone queries, inspired by Sirchmunk), auto-contradiction detection on ingest (flag when new source conflicts with existing wiki claims — not just at lint time), LLM keyword query expansion with strong-signal skip (pre-search scan-tier call generates 2 keyword-rich BM25 rewrites of the query; BM25 runs on all variants and results merged by max score; strong-signal skip: if top BM25 result normalized score ≥ 0.4 with 2× gap over rank-2, skip the expansion call entirely — one Haiku call per non-trivial query, zero cost on obvious lookups; inspired by sage-wiki's enhanced search pipeline).

**Phase 5 (deferred — prove need through real usage first):** Inline claim-level confidence tags with EXTRACTED lint verification (upgrade page-level `confidence` frontmatter with per-claim inline markers emitted during ingest: `[EXTRACTED]` for claims directly traceable to raw source text, `[INFERRED]` for reasoned conclusions, `[AMBIGUOUS]` for uncertain claims; modify ingest LLM prompts to emit these markers inline in wiki page bodies; `kb_lint_deep` gains a check that spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file, flagging hallucinated attributions — the direct answer to "LLM stated this as sourced fact but it's not actually in the source"; complements existing page-level confidence without replacing it — inspired by llm-wiki-skill's confidence annotation + lint verification model), URL-aware `kb_ingest` with 5-state adapter model (upgrade `kb_ingest` and `kb_ingest_content` to accept URLs directly alongside file paths; URL routing table in `kb.config` maps URL patterns to source type + `raw/` subdir + preferred adapter; before executing adapter, checks 5 explicit states: `not_installed` — adapter binary missing, `env_unavailable` — Chrome CDP not on port 9222 for JavaScript-heavy pages, `runtime_failed` — adapter ran with non-zero exit code, `empty_result` — adapter returned <100 chars, `unsupported` — no adapter matches this URL pattern; each state emits a specific recovery hint and offers manual-paste fallback; eliminates the current "run crwl first, save the file, then kb_ingest the file" three-step friction — inspired by llm-wiki-skill's adapter-state.sh 5-state model), Conversation capture `kb_capture` MCP tool (accept up to 50KB of raw conversation or note text; scan-tier LLM extracts discrete knowledge items — decisions, discoveries, corrections, gotchas — filtering out noise and retries; writes each as `raw/captures/<slug>.md` with `source: mcp-capture` frontmatter; returns filenames for subsequent `kb_ingest` compilation; fills the gap `kb_ingest_content` cannot handle because it expects already-structured content — inspired by sage-wiki's `wiki_capture`), chunk-level BM25 sub-page indexing (split wiki pages into ~600-token overlapping chunks at ingest time; each chunk gets its own BM25 index entry with id `<page_id>:c<n>`; query engine scores chunks, deduplicates to best chunk per page, then loads full pages for synthesis; backfill existing pages on first upgrade compile; resolves the core weakness where relevant content is buried in a long page — inspired by sage-wiki's FTS5 chunk indexing), typed semantic relations on graph edges (extract 6 relation types from article text via keyword matching — `implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`; stored as edge `relation_type` attribute on the NetworkX graph and in SQLite; enables typed graph traversal in `kb_query` and enriches multi-signal graph retrieval weight assignment — inspired by sage-wiki's configurable ontology), Interactive knowledge graph HTML viewer (self-contained vis.js HTML export from `kb_graph_viz` with `format=html` — dark theme, search bar, click-to-inspect nodes, community clustering via Louvain coloring, edge type legend; opens in any browser, no server — inspired by llm-wiki-agent's graph.html), semantic edge inference in graph (two-pass graph build: existing wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS with confidence 0–1; only re-infers changed pages via content hash cache; surfaces hidden connections humans forgot to wikilink — inspired by llm-wiki-agent), living overview page (single `wiki/overview.md` revised on every ingest to reflect current synthesis across all sources — always-current executive summary of the entire KB, updated as final step of ingest pipeline), actionable gap-fill source suggestions (enhance evolve to suggest specific real-world sources for each coverage gap — "no sources on mixture-of-experts, consider the Mixtral paper" — one LLM call per gap to produce actionable acquisition targets), two-phase compile pipeline (batch cross-source merging before writing), pre-publish validation gate, multi-signal graph retrieval (BM25 seed → 4-signal graph expansion: direct wikilinks ×3 + source-overlap ×4 for pages sharing a raw source + Adamic-Adar shared-neighbor similarity ×1.5 + type-affinity ×1; nodes ranked by combined BM25 + graph relevance score with budget-proportional context assembly — inspired by nashsu/llm_wiki's relevance model), answer trace enforcement (reject uncited claims), conversation→KB promotion (positively-rated query answers → wiki pages), temporal claim tracking (validity windows on individual claims within pages for staleness/contradiction resolution — MemPalace's SQLite KG with `valid_from`/`ended` dates as reference pattern), BM25 + LLM reranking (optional Haiku rerank pass for improved relevance at ~$0.001/query), semantic deduplication pre-ingest (embedding similarity check to catch same-topic-different-wording duplicates beyond content hash), wake-up context snapshot as bidirectional session cache (`wiki/hot.md` — ~500-word compressed context updated at session end, read at session start; includes key recent facts, recent page changes, and active threads/open questions; survives context compaction and session boundaries; enables cross-session continuity without full wiki crawl — enhanced from MemPalace concept with claude-obsidian's hot cache pattern), multi-mode search depth toggle (`depth=fast|deep` parameter on `kb_query` — fast uses current BM25, deep uses MC sampling for complex multi-hop questions), graph topology gap analysis in kb_evolve (augment topic-based coverage-gap analysis with structural signals: isolated pages with degree ≤ 1 = disconnected knowledge islands, bridge nodes connecting 3+ communities = high-value connection targets, cross-community surprising edges = implicit relationships worth surfacing — inspired by nashsu/llm_wiki's Graph Insights), cascade source deletion `kb_delete_source` MCP tool (remove raw source file + cascade: delete source summary wiki page, strip source from `source:` field of shared entity/concept pages without deleting them, clean dead wikilinks from remaining wiki pages, update index.md and _sources.md — fills the only major operational workflow gap not addressed by existing tooling), two-step CoT ingest analysis pass (split ingest into: analysis call producing structured output of entity list + connections to existing wiki + contradictions with existing claims + wiki structure recommendations; then generation call using analysis as context — improves extraction quality, enables richer contradiction flagging, and feeds directly into Phase 4's auto-contradiction detection on ingest — inspired by nashsu/llm_wiki's two-step chain-of-thought), wiki/purpose.md KB focus document (lightweight `wiki/purpose.md` defining KB goals, key questions, and research scope; included in query context and ingest system prompt for directional focus so the LLM biases extraction toward the KB's current direction — analogous to nashsu/llm_wiki's purpose.md, requires reading the file in `kb_query` and `ingest_source`), query answer instant-save (`save_as` parameter on `kb_query` MCP tool + `--save` CLI flag — immediately creates a `wiki/synthesis/{slug}.md` page from the query answer with citations mapped to `source:` refs and proper frontmatter; no feedback gate required, faster knowledge accumulation loop for high-confidence answers; coexists with deferred conversation→KB promotion for uncertain ones — inspired by llm-wiki-agent's interactive save), PageRank-prioritized semantic lint sampling (when `kb_lint_deep` must limit its page budget, select pages by PageRank descending rather than arbitrary order; high-authority pages with quality issues have outsized downstream impact on citing pages — zero-cost improvement once PageRank scores are available from `graph_stats`), community-aware retrieval boost (after Louvain community detection, persist community IDs per page; during `query_wiki`, pages sharing a community with BM25 top-K hits get a relevance boost as 5th signal in multi-signal graph retrieval — topical neighborhoods surface related context that BM25 keyword overlap alone misses; depends on interactive graph viewer shipping first for community computation — inspired by llm-wiki-agent's Louvain clustering), page status lifecycle frontmatter (`status: seed|developing|mature|evergreen` field orthogonal to `confidence`; seed = stub or single-source page, developing = multi-source but incomplete, mature = well-sourced and reviewed, evergreen = stable reference; evolve targets seed pages for enrichment, lint flags mature pages not updated in 90+ days as potentially stale, query engine applies mild ranking boost to mature/evergreen pages over seed; status transitions via `kb_refine_page` or explicit `kb_lint --fix` — inspired by claude-obsidian's page lifecycle), inline quality callout markers (embed structured `> [!contradiction]`, `> [!gap]`, `> [!stale]`, `> [!key-insight]` callouts within wiki page body text at the point of relevance; complements centralized `wiki/contradictions.md` by making quality signals discoverable when reading any individual page; lint parses callouts for aggregate reporting — "3 pages have unresolved contradictions, 7 have gaps"; ingest auto-inserts `[!contradiction]` when auto-contradiction detection fires; renders natively in Obsidian as styled callout blocks — inspired by claude-obsidian's custom callout system), autonomous research loop in `kb_evolve` (`mode=research` parameter — for each identified coverage gap, decompose into 2–3 web search queries, fetch top results via fetch MCP, save to `raw/articles/` via `kb_save_source`, return file paths for subsequent `kb_ingest`; max 3 rounds of progressive refinement per gap — round 1 broad search, round 2 fills remaining sub-gaps, round 3 resolves contradictions; capped at 5 sources per gap to prevent runaway ingestion; requires fetch MCP server; turns evolve from advisory gap report into actionable source acquisition pipeline — inspired by claude-obsidian's autoresearch skill).

**Phase 6 (cut — revisit only if real usage demands it):** DSPy Teacher-Student optimization, RAGAS evaluation, Monte Carlo evidence sampling (Sirchmunk-inspired DEEP search mode), conversation segment classification (MemPalace mining modes), pattern-based source pre-classification (regex heuristics to classify content type before LLM extraction), exchange-pair chunking for conversation sources (preserve Q+A dialogue structure instead of flat text).

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
