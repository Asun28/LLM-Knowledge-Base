# MCP Servers
<!-- FORMAT GUIDE
Purpose: MCP server catalogue — what each server does, key tools, and configuration notes.
- Add a new section when a new MCP server is added to .mcp.json.
- Update a section when a server's key tools or configuration change significantly.
- Do NOT list every tool parameter here — just the purpose, key tools, and any non-obvious config.
-->

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "MCP Servers" section. Pairs with [workflows.md](workflows.md) (Phase 2 workflows that use these tools) and [ingestion-commands.md](ingestion-commands.md).

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

## Key usage

- **kb** — The knowledge base MCP server (`kb.mcp_server`, 28 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question, output_format="", save_as="")` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis. Add `output_format={markdown|marp|html|chart|jupyter}` (requires `use_api=true`) to render the synthesized answer to a file under `outputs/`. `text` or empty = default stdout-only. Cycle 16: `save_as=<slug>` (requires `use_api=true`) persists the synthesised answer to `wiki/synthesis/{slug}.md` with hardcoded frontmatter (`type=synthesis`, `confidence=inferred`, `authored_by=llm`; `source` derived from the query's `source_pages`). `save_as` must match `[a-z0-9-]+`; traversal / Unicode homoglyph / Windows reserved names rejected with error strings. Low-coverage refusal path skips the save. Note: this makes `kb_query` a write path when `save_as` is set.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction. Output includes `affected_pages` (cascade review list) and `wikilinks_injected` (pages updated with retroactive links). Shows "Duplicate content detected" with hash if source was already ingested.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename, overwrite=false)` — save content to `raw/` for later ingestion. Returns error if file already exists unless `overwrite=true`.
  - `kb_capture(content, provenance=None)` — atomize up to 50KB of unstructured text into discrete `raw/captures/<slug>.md` items via scan-tier LLM. Returns file paths for subsequent `kb_ingest`. Secret-scanner rejects content with API keys, tokens, or private key blocks before any LLM call.
  - `kb_compile_scan(wiki_dir=None)` — find changed sources, then `kb_ingest` each. `wiki_dir` scopes changed-source discovery to that wiki project's sibling `raw/` and `.data/` paths.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint(fix=False, augment=False, dry_run=False, execute=False, auto_ingest=False, max_gaps=5, wiki_dir=None)` — health checks (dead links, orphans, staleness, stub detection, flagged pages). With `augment=True`, runs reactive gap-fill in three opt-in modes: `propose` (default — writes `wiki/_augment_proposals.md`), `execute=True` (fetches URLs to `raw/`), `auto_ingest=True` (pre-extracts at scan tier + ingests with `confidence: speculative`). `wiki_dir` also scopes feedback-derived sections to `<project>/.data/feedback.json`. See `docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md`. Plus `kb_evolve(wiki_dir=None)` (includes coverage gaps + stub enrichment suggestions; feedback gaps are scoped to the wiki project), `kb_detect_drift` (finds wiki pages stale due to raw source changes), `kb_graph_viz` (Mermaid graph export with auto-pruning), `kb_verdict_trends` (weekly quality dashboard).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
  - **Concurrency model** (cycle 95) — FastMCP runs sync tools via `anyio.to_thread.run_sync`, which draws from the **default thread limiter** (capacity 40, held per event loop in an anyio `RunVar` — not process-wide), and a tool holds its token for its whole runtime. **14 LONG tools** are therefore registered as async wrappers by `kb.mcp._offload.register_long_tool` and offloaded to a **dedicated per-event-loop `anyio.CapacityLimiter`** (default 8, `KB_MCP_LONG_TOOL_THREADS`), so a batch of concurrent compiles cannot queue sub-second reads like `kb_search` behind them. Kill-switch `KB_DISABLE_MCP_LONG_TOOL_LIMITER=1` routes them back onto the default limiter.
    - **Classification rule** — long = makes an LLM/network call **or** does unbounded whole-corpus work. "Makes no LLM call" does not make a tool short: `kb_evolve` measured 4.96–11.25s (loads the wiki, scores up to 50,000 connection pairs) and `kb_stats` 2.63–7.37s cold (fingerprints every page, rebuilds the graph under `graph.cache._CACHE_LOCK`, runs PageRank). The 14: LLM/network — `kb_query`, `kb_lint`, `kb_compile`, `kb_ingest`, `kb_ingest_content`, `kb_capture`; whole-corpus — `kb_evolve`, `kb_stats`, `kb_graph_viz`, `kb_detect_drift`, `kb_compile_scan`, `kb_lint_consistency`, `kb_refine_page`, `kb_affected_pages` (the last two rebuild the whole-wiki backlink map).
    - **Terminology** — a custom `CapacityLimiter` is an **admission budget**, not a separate pool of reserved threads: anyio keeps one worker-thread collection per event loop and applies the limiter as a gate around it, so total live workers can reach roughly default capacity + long-tool capacity.
    - The module attributes stay plain sync callables — importing `kb.mcp.health.kb_lint` and calling it directly is unaffected.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.
