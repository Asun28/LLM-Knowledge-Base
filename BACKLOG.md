# Backlog

<!-- FORMAT GUIDE — read before adding items
Each phase section groups items by severity, then by module area.
Resolved phases collapse to a one-liner; active phases list every item.

## Severity Levels

| Level      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| CRITICAL   | Data loss, crash with no recovery, or security exploit — blocks release |
| HIGH       | Silent wrong results, unhandled exceptions reaching users, reliability risk |
| MEDIUM     | Quality gaps, missing test coverage, misleading APIs, dead code |
| LOW        | Style, docs, naming, minor inconsistencies — fix opportunistically |

## Item Format

```
- `module/file.py` `function_or_symbol` — description of the issue
  (fix: suggested remedy if non-obvious)
```

Rules:
- Lead with the file path (relative to `src/kb/`), then the function/symbol.
- Include line numbers only when they add precision (e.g. `file.py:273`).
- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
- One bullet = one issue. Don't combine unrelated problems.
- When resolving an item, delete it (don't strikethrough). Record the fix in CHANGELOG.md.
- Move resolved phases under "## Resolved Phases" with a one-line summary.
-->

---

## Phase 4 (v0.10.0) — Post-release audit

_All items resolved — see `CHANGELOG.md` `[Unreleased]`._

---

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

### HIGH LEVERAGE — Epistemic Integrity 2.0

- `models/` `belief_state` frontmatter — add `belief_state: confirmed|uncertain|contradicted|stale|retracted` field orthogonal to `confidence`. `belief_state` is the cross-source aggregate (lint-propagated); `confidence` stays per-source attribution. Query engine filters/weights on belief_state; lint updates it when contradictions or staleness are detected. Source: epistemic-mapping proposal (dangleh, gist).
  (effort: Low — one frontmatter field + propagation rules in `lint/checks.py` and query ranking)

- `ingest/pipeline.py` `source` subsection-level provenance — allow `source: raw/file.md#heading` or `raw/file.md:L42-L58` deep-links in frontmatter; ingest extractor captures heading context so citations point at the actual section that grounds the claim. Source: Agent-Wiki (kkollsga, gist — two-hop citation traceability).
  (effort: Medium — extractor update + citation renderer + backlink resolver for the new form)

- `lint/drift.py` `kb_drift_audit` — cold re-ingest a random sample of raw sources with no prior wiki context, diff against current wiki pages, surface divergence as "potential LLM drift" warnings. Different from existing `kb_detect_drift` which checks source mtime changes; this catches *wiki-side* drift where compilation has diverged from source truth. Source: Memory Drift Prevention (asakin, gist — cites ETH Zurich study: auto-generated context degraded 5/8 cases).
  (effort: Medium — new module; reuse existing `ingest_source` with `wiki_dir=tmp` then diff)

- `compile/merge.py` `kb_merge <a> <b>` + `lint/checks.py` duplicate-slug — lint detects near-duplicate slugs (`attention` vs `attention-mechanism`, `rag` vs `retrieval-augmented`); `kb_merge` MCP tool merges two pages, updates all backlinks across `wiki/` and `wiki/outputs/`, archives absorbed page to `wiki/archive/` with a redirect stub, one git commit per merge. Source: Louis Wang.
  (effort: Medium — merge is the new work; dup-slug detection adds one lint check)

- `query/engine.py` coverage-confidence gate — compute mean cosine similarity between query and top-K results; if <0.45, return "low confidence" warning with LLM-suggested rephrasings instead of synthesizing a mediocre answer. Source: VLSiddarth Knowledge-Universe.
  (effort: Low — threshold check after existing hybrid search; use scan-tier LLM for rephrasing)

- `models/` `authored_by: human|llm|hybrid` frontmatter — formalize human-written vs LLM-generated pages; query engine applies mild weight boost to human-authored; lint flags user-declared human pages that have been auto-edited by ingest without flag removal. Source: PKM-vs-research-index critique (gpkc, gist).
  (effort: Low — one field + ranking hook + lint rule)

- `ingest/pipeline.py` `lint/semantic.py` inline claim-level confidence tags — emit `[EXTRACTED]`, `[INFERRED]`, `[AMBIGUOUS]` inline markers in wiki page bodies during ingest; modify ingest LLM prompts to annotate individual claims at source; `kb_lint_deep` spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file, flagging hallucinated attributions. Complements page-level `confidence` frontmatter without replacing it; directly answers "LLM stated this as sourced fact but it's not in the source." Source: llm-wiki-skill confidence annotation + lint verification model.
  (effort: Medium — ingest prompt update + regex claim parser + lint spot-check against raw source text)

### HIGH LEVERAGE — Output-Format Polymorphism

- `query/formats/` `kb_query --format={text|marp|html|chart|jupyter}` — adapters file output under `wiki/outputs/` with provenance linking back to query + contributing pages. Directly addresses Karpathy's tweet: *"render markdown files, slide shows (Marp format), matplotlib images"*. Source: Karpathy tweet + Fabian Williams + JupyterBook reply.
  (effort: Medium — one adapter per format; matplotlib adapter emits a Python script first, optional server-side render)

- `compile/publish.py` `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` — auto-generate AI-agent-consumable outputs alongside markdown during compile: each page gets `.txt`/`.json` siblings; wiki root gets `/llms.txt`, `/graph.jsonld`, `/sitemap.xml`. Makes the wiki itself a retrievable source for other agents. Source: Pratiyush/llm-wiki.
  (effort: Low — renderers over existing frontmatter + graph)

- `lint/augment.py` `kb_lint --augment` — action-mode lint: when a gap is detected (missing entity, unresolved citation, stub page), pull missing data via `fetch` MCP and append as a new raw source, re-ingesting automatically. Distinct from deferred `kb_evolve --research` (proactive gap-filling); this is reactive to lint findings. Source: Karpathy tweet (*"impute missing data with web searchers"*).
  (effort: Medium — lint check → fetch adapter → ingest dispatcher)

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass modeled on biological memory consolidation: NREM (new events → concepts, cross-event pattern extraction), REM (contradiction detection → mark old edges `superseded` rather than delete), Pre-Wake (graph health audit). Runs as nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three distinct sub-passes; overlaps with existing lint/evolve but with "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics to surface cross-domain connections. New query mode beyond retrieval. Source: Elvis Saravia reply (*"O(n^k) synthesis across k domains — stoic philosophy × saas pricing × viral content × parenting"*).
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3 since path count explodes)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice (standalone blob) loadable into voice-mode LLMs or mobile clients. Addresses *"interactive podcast while running"* use case. Source: Lex-style reply.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `mcp/` `kb_capture` MCP tool — accept up to 50KB of conversation or note text; scan-tier LLM extracts discrete knowledge items (decisions, discoveries, corrections, gotchas) and filters noise; writes each item to `raw/captures/<slug>.md` with `source: mcp-capture` frontmatter; returns filenames for subsequent `kb_ingest`. Fills the gap `kb_ingest_content` cannot handle (it expects already-structured content). Source: sage-wiki `wiki_capture`.
  (effort: Medium — scan-tier extraction prompt + raw/captures/ directory convention + per-item slug writer)

- `ingest/session.py` — auto-ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. Distinct from `kb_capture` (user-triggered, any text) and deferred "conversation→KB promotion" (positive-rated query answers only): this is ambient, runs on every session. Source: Pratiyush/llm-wiki.
  (effort: Medium — JSONL parsers per agent + dedup against existing raw/conversations/)

- `hooks/` `SessionStart` hook + `raw/` file watcher — hooks auto-sync on every Claude Code launch; file watcher with debounce triggers ingestion on new files in `raw/` without explicit CLI invocation. Source: Pratiyush/llm-wiki + Memory-Toolkit (IlyaGorsky, gist).
  (effort: Low — Claude Code hook + `watchdog` file observer)

- `ingest/filter.py` `.llmwikiignore` + secret scanner — pre-ingest regex-based secret/PII filter (API keys, tokens, passwords, paths on `.llmwikiignore`); rejects or redacts before content leaves local. Missing safety rail given every ingest currently sends full content to the API. Source: rohitg00 LLM Wiki v2 + Louis Wang security note.
  (effort: Low — `detect-secrets`-style regex list + glob-pattern ignore)

- `_raw/` staging directory — vault-internal drop-and-forget directory for clipboard pastes / rough notes; next `kb_ingest` promotes to `raw/` and removes originals. Distinct from `raw/` (sourced documents) and deferred `kb_capture` (explicit tool). Source: Ar9av/obsidian-wiki.
  (effort: Low — directory convention + promotion step in ingest)

- `ingest/pipeline.py` per-subdir ingest rules — infer source type from `raw/web/`, `raw/papers/`, `raw/transcripts/` subdirectory rather than requiring explicit `--type` argument. Source: Fabian Williams.
  (effort: Low — path→type lookup table; `--type` stays as override)

### MEDIUM LEVERAGE — Refinements to existing Phase 5 deferred items

- Deferred "multi-signal graph retrieval" — use empirical weights 3 (direct link) / 4 (source-overlap) / 1.5 (Adamic-Adar) / 1 (type-affinity). Source: nashsu/llm_wiki (concrete ratios from production use).
  (effort: N/A — parameter choice for the existing deferred item)

- Deferred "community-aware retrieval boost" — Louvain intra-edge density <0.15 = "sparse/weak" threshold; surface sparse communities in `kb_evolve`. Source: nashsu.
  (effort: N/A — threshold choice)

- Deferred "stale flagging at query time" — per-platform decay half-lives: HuggingFace 120d, GitHub 180d, StackOverflow 365d, arXiv 1095d, Wikipedia 1460d, OpenLibrary 1825d; ×1.1 volatility multiplier on LLM/React/Docker/Claude topics. Replaces single-threshold staleness. Source: VLSiddarth.
  (effort: Low delta on the existing deferred item — `SOURCE_DECAY_DAYS` dict in config)

- `query/engine.py` `CONTEXT_TIER1_BUDGET` → 60/20/5/15 split (wiki pages / chat history / index / system) instead of single 20K-of-80K split. Source: nashsu.
  (effort: Low — replace single constant with proportional calculator)

- Deferred "graph topology gap analysis" — expose as card types: "Isolated (degree ≤ 1)", "Bridge (connects ≥ 3 clusters)", "Sparse community (cohesion < 0.15)" — each with one-click trigger that dispatches `kb_evolve --research` on the specific gap. Source: nashsu.
  (effort: N/A — card-type taxonomy for existing deferred item)

### LOW LEVERAGE — Operational

- `wiki/_schema.md` vendor-neutral single source of truth — move project schema (page types, frontmatter fields, wikilink syntax, operation contracts) out of tool-convention files and into `wiki/_schema.md` co-located with the data it describes. Existing `CLAUDE.md` / future `AGENTS.md` / `GEMINI.md` stay as thin (~10-line) vendor shims that point at `_schema.md` for project rules. Schema is machine-parseable (fenced YAML blocks under markdown headers) and validated by lint on every ingest. Innovation vs. the common "symlink AGENTS.md → CLAUDE.md" pattern: the schema lives WITH the wiki, portable across agent frameworks (Codex, Cursor, Gemini CLI, shell scripts). Follows the existing `_sources.md` / `_categories.md` convention. Source: Karpathy tweet (schema portability prompt) + project design.
  (effort: Medium — (a) write `wiki/_schema.md` starter as self-describing meta page; (b) `kb.schema.load()` parser; (c) `kb_lint` integration validates frontmatter against schema; (d) `schema_version` + `kb migrate` CLI; (e) optional multi-persona sections `### for ingest` / `### for query` / `### for review` so agents load scoped context. Defer vendor shim updates — keep `CLAUDE.md` unchanged until user chooses to slim it)

- `cli.py` `kb search <query>` subcommand — colorized terminal output over the existing hybrid search; `kb search --serve` exposes a minimal localhost web UI. Power-user CLI over the same engine the LLM already uses via MCP. Source: Karpathy tweet (*"small and naive search engine, web ui and CLI"*).
  (effort: Low — Click command + Flask/FastAPI localhost UI)

- Git commit receipts on ingest — emit `"four new articles appeared: Amol Avasari, Capability Overhang, CASH Framework, Success Disasters"` style summary with commit hash and changed files per source. Source: Fabian Williams.
  (effort: Low — wrap existing ingest return dict with a formatter)

### HIGH LEVERAGE — Ingest & Query Convenience

- `mcp/core.py` `kb_ingest` URL-aware 5-state adapter — upgrade `kb_ingest`/`kb_ingest_content` to accept URLs alongside file paths; URL routing table in `kb.config` maps patterns to source type + `raw/` subdir + preferred adapter; before executing, checks 5 explicit states: `not_installed`, `env_unavailable`, `runtime_failed`, `empty_result`, `unsupported` — each emits a specific recovery hint and offers manual-paste fallback. Eliminates the "run crwl, save file, then kb_ingest file" three-step friction. Source: llm-wiki-skill adapter-state.sh 5-state model.
  (effort: Medium — URL routing table in config + per-state error handling + adapter dispatcher)

- `mcp/core.py` `kb_delete_source` MCP tool — remove raw source file and cascade: delete source summary wiki page, strip source from `source:` field on shared entity/concept pages without deleting them, clean dead wikilinks from remaining wiki pages, update `index.md` and `_sources.md`. Fills the only major operational workflow gap not addressed by existing tooling.
  (effort: Medium — cascade deletion logic + backlink cleanup + atomic index/sources update)

- `mcp/core.py` `kb_query` `save_as` parameter — immediately create a `wiki/synthesis/{slug}.md` page from the query answer with citations mapped to `source:` refs and proper frontmatter; no feedback gate required, faster knowledge accumulation for high-confidence answers. Coexists with feedback-gated conversation→KB promotion as the immediate save path. Source: llm-wiki-agent interactive save.
  (effort: Low — slug from question + frontmatter builder + atomic write; CLI `--save` flag mirrors it)

- `evolve/analyzer.py` `kb_evolve mode=research` — for each identified coverage gap, decompose into 2–3 web search queries, fetch top results via fetch MCP, save to `raw/articles/` via `kb_save_source`, return file paths for subsequent `kb_ingest`; capped at 5 sources per gap, max 3 rounds (broad → sub-gaps → contradictions). Turns evolve from advisory gap report into actionable source acquisition pipeline. Source: claude-obsidian autoresearch skill.
  (effort: Medium — gap decomposition prompt + fetch MCP integration + 3-round loop with source cap)

- `wiki/purpose.md` KB focus document — lightweight file defining KB goals, key questions, and research scope; included in `kb_query` context and ingest system prompt so the LLM biases extraction toward the KB's current direction. Source: nashsu/llm_wiki purpose.md.
  (effort: Low — one markdown file + read in query_wiki + prepend in ingest system prompt)

### MEDIUM LEVERAGE — Search & Indexing

- `query/bm25.py` `query/embeddings.py` chunk-level sub-page indexing — split wiki pages into topically coherent chunks using Savitzky-Golay boundary detection (embed sentences with model2vec, compute adjacent cosine similarities, SG smoothing 5-window 3rd-order polynomial, find zero-crossings as topic boundaries); each chunk indexed as `<page_id>:c<n>`; query engine scores chunks, deduplicates to best chunk per page, loads full pages for synthesis. Resolves the weakness where relevant content is buried in long pages. Source: garrytan/gbrain semantic.ts + sage-wiki FTS5 chunking.
  (effort: High — SG chunking module + BM25 index schema change + chunk-to-page dedup aggregation layer)

- `compile/linker.py` cross-reference auto-linking — when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` added to A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`. Builds graph density automatically without requiring typed relations. Source: garrytan/gbrain ingest cross-reference link creation.
  (effort: Low — post-injection pass over co-mentioned entity pairs; reuses existing inject_wikilinks infrastructure)

- `lint/checks.py` `query/engine.py` PageRank-prioritized semantic lint sampling — when `kb_lint_deep` must limit its page budget, select pages by PageRank descending rather than arbitrary order; high-authority pages with quality issues have outsized downstream impact on citing pages. Source: existing `graph_stats` PageRank scores.
  (effort: Low — sort by graph_stats PageRank before sampling; zero new infrastructure required)

### MEDIUM LEVERAGE — Page Lifecycle & Quality Signals

- `models/` `status` frontmatter field — `status: seed|developing|mature|evergreen` orthogonal to `confidence`; seed = stub/single-source, developing = multi-source but incomplete, mature = well-sourced + reviewed, evergreen = stable reference. `kb_evolve` targets seed pages; lint flags mature pages not updated in 90+ days as potentially stale; query engine applies mild ranking boost to mature/evergreen. Source: claude-obsidian page lifecycle.
  (effort: Low — one frontmatter field + rule hooks in evolve, lint, and query ranking)

- `wiki/` inline quality callout markers — embed `> [!contradiction]`, `> [!gap]`, `> [!stale]`, `> [!key-insight]` callouts at the point of relevance in wiki page bodies; lint parses callouts for aggregate reporting ("3 pages have unresolved contradictions"); ingest auto-inserts `[!contradiction]` when auto-contradiction detection fires; renders natively in Obsidian. Source: claude-obsidian custom callout system.
  (effort: Low — callout emitter in ingest/contradiction.py + lint parser for aggregate counts)

- `wiki/hot.md` wake-up context snapshot — ~500-word compressed context updated at session end (recent facts, recent page changes, open questions); read at session start via `SessionStart` hook; survives context compaction and session boundaries; enables cross-session continuity without full wiki crawl. Source: MemPalace concept + claude-obsidian hot cache.
  (effort: Low — append-on-ingest + SessionStart hook reads + one markdown file)

- `wiki/overview.md` living overview page — auto-revised on every ingest as the final pipeline step; always-current executive summary across all sources; updated not replaced on each ingest. Source: llm-wiki-agent living overview.
  (effort: Low — scan-tier LLM over index.md + top pages; one file auto-updated per ingest)

### MEDIUM LEVERAGE — Knowledge Promotion & Ingest Quality

- `query/engine.py` `feedback/store.py` conversation→KB promotion — positively-rated query answers (rating ≥ 4) auto-promote to `wiki/synthesis/{slug}.md` pages with citations mapped to `source:` refs; coexists with `save_as` parameter (immediate, no gate) as the feedback-gated deferred path. Source: garrytan/gbrain maintain skill.
  (effort: Medium — feedback store hook + synthesis page writer + conflict check against existing pages)

- `ingest/pipeline.py` two-step CoT ingest analysis pass — split ingest into: (1) analysis call producing entity list + connections to existing wiki + contradictions + wiki structure recommendations; (2) generation call using analysis as context. Improves extraction quality and enables richer contradiction flagging; feeds Phase 4 auto-contradiction detection. Source: nashsu/llm_wiki two-step chain-of-thought.
  (effort: Medium — split single ingest LLM call into two sequential calls with analysis-as-context)

### Phase 6 candidates (larger scope, not yet scheduled)

- Hermes-style independent quality-gate supervisor — different-model-family validator (not same-family self-review) before page promotion. Source: Secondmate (@jumperz, via VentureBeat).
  (effort: High — adds a second provider; challenges fail-open defaults)

- Mesh sync for multi-agent writes — last-write-wins with timestamp conflict resolution; private-vs-shared scoping (personal preferences private, architecture decisions shared). Source: rohitg00.
  (effort: High — assumes multi-writer concurrency model)

- Hosted MCP HTTP/SSE variant — multi-device access (phone Claude app, ChatGPT, Cursor, Claude Code) reading/writing the same KB. Source: Hjarni/dev.to.
  (effort: High — MCP transport + auth; currently stdio-only)

- Personal-life-corpus templates — Google Takeout / Apple Health / AI session exports / bank statements as a domain starter kit. Privacy-aware ingest layered on `.llmwikiignore`. Source: anonymous personal-data-RAG reply.
  (effort: Medium — per-source-type extractor templates; depends on `.llmwikiignore` landing first)

- Multi-signal graph retrieval — BM25 seed → 4-signal graph expansion: direct wikilinks ×3 + source-overlap ×4 + Adamic-Adar shared-neighbor similarity ×1.5 + type-affinity ×1; nodes ranked by combined BM25 + graph score with budget-proportional context assembly. Prerequisite: typed semantic relations (below). Source: nashsu/llm_wiki relevance model.
  (effort: High — graph score combination layer + per-signal weight tuning + typed relations as prerequisite)

- Typed semantic relations on graph edges — extract 6 relation types via keyword matching: `implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`; stored as edge attribute in NetworkX + SQLite; enables typed graph traversal in `kb_query`. Prerequisite for multi-signal retrieval. Source: sage-wiki configurable ontology.
  (effort: Medium — relation extractor pass + NetworkX/SQLite graph schema update)

- Temporal claim tracking — `valid_from`/`ended` date windows on individual claims within pages; enables staleness/contradiction resolution at claim granularity rather than page granularity. Requires new SQLite KG schema. Source: MemPalace SQLite KG pattern.
  (effort: High — claim-level SQLite schema + ingest extractor update + query-time filtering)

- Semantic edge inference in graph — two-pass graph build: existing wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS with confidence 0–1; re-infers only changed pages via content hash cache. Source: llm-wiki-agent.
  (effort: High — 2-pass build logic + confidence-weighted edges + per-page change detection)

- Answer trace enforcement — require synthesizer to tag every factual claim with `[wiki/page]` or `[raw/source]` citation at synthesis time; post-process strips or flags uncited claims as gaps. Source: epistemic integrity requirement.
  (effort: High — synthesis prompt rewrite + citation parser + enforcement pass + graceful fallback)

- Multi-mode search depth toggle (`depth=fast|deep`) — `depth=deep` uses Monte Carlo evidence sampling for complex multi-hop questions; `depth=fast` is current BM25 hybrid. Depends on MC sampling infrastructure. Source: Sirchmunk Monte Carlo evidence sampling.
  (effort: High — MC sampler architecture + budget allocation + fast/deep routing logic)

- Semantic deduplication pre-ingest — embedding similarity check before ingestion to catch same-topic-different-wording duplicates beyond content hash; flag if cosine similarity >0.85 to any existing raw source. Source: content deduplication research.
  (effort: Medium — embed new source + nearest-neighbor check vs existing vector store)

- Interactive knowledge graph HTML viewer — self-contained vis.js HTML export from `kb_graph_viz` with `format=html`; dark theme, search bar, click-to-inspect nodes, Louvain community clustering, edge type legend. Source: llm-wiki-agent graph.html.
  (effort: Medium — vis.js template + Louvain community IDs per node + edge type legend)

- Two-phase compile pipeline + pre-publish validation gate — phase 1: batch cross-source merging before writing; phase 2: validation gate rejects pages with unresolved contradictions or missing required citations. Architecture change to current single-pass compiler. Source: compilation best practices.
  (effort: High — compiler refactor into two phases + validation gate + publish/reject state machine)

- Actionable gap-fill source suggestions — enhance `kb_evolve` to suggest specific real-world sources for each gap ("no sources on MoE, consider the Mixtral paper"). Mostly superseded by `kb_evolve mode=research` (Phase 5) which fetches sources autonomously; keep as fallback for offline/no-fetch environments. Source: nashsu/llm_wiki.
  (effort: Low delta on evolve — add one LLM call per gap; ship only if mode=research is blocked)

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision, same failure mode as Evernote's "which folder" and Notion's "which tag". Document that our model merges aggressively and that atomic-note alternative exists.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; our counter is evidence-trail provenance plus two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion, not optional.

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
- **Phase 4 post-release audit** — all items resolved (23 HIGH + ~30 MEDIUM + ~30 LOW) in CHANGELOG.md [Unreleased]
