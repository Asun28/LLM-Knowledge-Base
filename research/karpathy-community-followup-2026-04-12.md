# Karpathy Community Followup: Net-New Roadmap Inspirations

*Researched 2026-04-12. Sources: Karpathy's original X post (Apr 2, 2026 · 18.9M views · 6.4K replies), gist comment thread, long-tail reply thread via xcancel + HN + Medium + dev.to + Ghost + VentureBeat, and 12+ community fork repos. Content here is **net-new**: ideas not already captured in `research/karpathy-llm-knowledge-bases-analysis.md`, `research/gbrain-analysis.md`, `research/project-ideas.md`, or the Phase 5/6 deferred list in `CLAUDE.md`.*

---

## What this doc adds

The original analysis file absorbed the top ~15 community voices. The Phase 5/6 deferred list absorbed ~35 ideas from 5 fork repos (claude-obsidian, llm-wiki-agent, sage-wiki, nashsu/llm_wiki, garrytan/gbrain, llm-wiki-skill). Since then the thread has grown to 18.9M views with a long tail of substantive replies, a dozen more fork repos, and several Medium/dev.to/HN postmortems. This doc captures **only the material that is not already in those files or the deferred list**.

---

## New signals from Karpathy's own tweet (verbatim re-read)

Re-reading the tweet text now that we have it in full surfaces four concrete behaviors our system doesn't yet do, independent of community replies:

### 1. Output-format polymorphism

Karpathy: *"Instead of getting answers in text/terminal, I like to have it render markdown files for me, or slide shows (Marp format), or matplotlib images, all of which I then view again in Obsidian. You can imagine many other visual output formats depending on the query."*

**Our state:** `kb_query` returns text answers with citations. Nothing else.

**Proposal:** `format` parameter on `kb_query` with adapters — `text` (default), `marp` (slide deck), `chart` (matplotlib script or rendered PNG), `html` (interactive JS with sort/filter), `jupyter` (JupyterBook HTML report). Outputs file back into `wiki/outputs/` with provenance linking back to the query and contributing pages.

### 2. Lint that FILLS gaps (not just reports)

Karpathy: *"I've run some LLM 'health checks' over the wiki to e.g. find inconsistent data, **impute missing data (with web searchers)**, find interesting connections for new article candidates."*

**Our state:** `kb_lint` produces a report. `kb_evolve` suggests gaps. Neither fills them.

**Proposal:** `kb_lint --augment` (or `--fill`) pulls missing data via `fetch` MCP when a gap is detected and appends it as a new raw source, re-ingesting automatically. Action-mode lint complements report-mode lint.

### 3. Naive search engine as CLI tool handoff

Karpathy: *"I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries."*

**Our state:** We have BM25+hybrid search internally and `kb_search` MCP tool. No standalone CLI search subcommand with a web UI.

**Proposal:** `kb search <query>` subcommand exposes the same BM25+vector hybrid with colorized terminal output, plus `kb search --serve` for a minimal localhost web UI. Power tool for the human; same engine the LLM already uses via MCP.

### 4. Schema file is `AGENTS.md`, not `CLAUDE.md`

Karpathy: *"The schema is kept up to date in AGENTS.md."*

**Our state:** We use `CLAUDE.md`.

**Proposal:** Ship `AGENTS.md` as a portable alias (symlink or generated copy) so the KB works with Codex, Cursor, Droid, Gemini CLI, and others that standardized on `AGENTS.md`. Low effort; widens distribution.

---

## New signals from the reply thread (organized by theme)

### Theme A — Epistemic integrity 2.0

The thread surfaced specific techniques beyond Kepano's vault separation and the evidence-trail pattern we already have.

**A1. Sleep-cycle consolidation (ICPandaDAO / Anda Hippocampus).** Scheduled async passes modeled on biological memory consolidation: NREM consolidates new events into concepts, REM detects contradictions, Pre-Wake audits graph health. *"Old relationship not deleted; marked as `superseded`, noting when it was replaced and by what."* 
→ **Gap filled:** our lint is on-demand. A nightly or background `kb_consolidate` pass that runs these three jobs in sequence would catch drift before it compounds, and `superseded` as a first-class edge state is more honest than deletion.

**A2. Ebbinghaus-decayed per-claim confidence (rohitg00 / LLM Wiki v2).** *"When the LLM writes 'Project X uses Redis for caching,' that claim should know it came from two sources, was last confirmed three weeks ago, and sits at confidence 0.85."* Per-claim, not per-page; confidence decays over time, reinforces on re-confirmation.
→ **Gap filled:** our Phase 5 deferred "inline confidence tags" is static. Decay + reinforcement makes `stale: bool` continuous.

**A3. Memory tier taxonomy (rohitg00).** Working → Episodic → Semantic → Procedural. A frontmatter field upgrade beyond `confidence: stated|inferred|speculative`.
→ **Gap filled:** orthogonal dimension to confidence. Working = active session scratch, Episodic = "on 2026-04-12 I ingested X", Semantic = distilled concept, Procedural = how-to recipe.

**A4. Sensitive-data ingest filter + `.llmwikiignore` (rohitg00, Louis Wang, Pratiyush).** *"Before anything hits the wiki, strip sensitive data. API keys, tokens, passwords, anything marked private."* Louis Wang adds the missing framing: *"Every ingest sends content to Anthropic's API. The system has no concept of 'sensitive' vs 'non-sensitive' content — it treats everything you feed it the same way."*
→ **Gap filled:** no regex-based secret scanning in our ingest. `.llmwikiignore` gives the user a standard allow/deny.

**A5. Anchored human-audit queue (lewislulu / llm-wiki-skill).** Human highlights text in Obsidian or a web viewer; severity-tagged comment written to `audit/` as anchored markdown; agent processes the queue.
→ **Gap filled:** our `kb_query_feedback` is coarse (per-query rating). Anchored per-claim audit is finer and asynchronous — the human can flag during reading, not just post-query.

**A6. Independent quality-gate supervisor (@jumperz / Secondmate via VentureBeat).** 10-agent "Swarm Knowledge Base" managed via OpenClaw with **Hermes model (Nous Research) as independent quality-gate supervisor** — different model family validates every draft before promotion. *"Compound Loop: agents dump raw outputs → compiler organizes → Hermes validates → verified briefings fed back to agents at session start."*
→ **Gap filled:** our review is same-family (Claude reviewing Claude output). Cross-family validation is a structurally different signal.

**A7. Vibe-thinking critique (HN long-form reply).** *"Deep writing means coming up with things through the process of producing. If you're only letting AI produce while you only come up with questions, you might not actually be thinking."*
→ **Concrete design response:** defend the "authored_by: human|llm|hybrid" distinction with a lint check that flags user-declared human pages when they've been auto-edited by ingest.

---

### Theme B — Output modes beyond text

**B1. Dynamic HTML with JS controls (Lex-style replies, Elvis Saravia, Fabian Williams, Pratiyush).** Generate self-contained HTML with interactive sort/filter/viz. Fabian's concrete pattern: `/kb-output --slides <question>` and `/kb-output --chart`.

**B2. Mini-KB export for voice mode (Lex-style reply).** *"The system generate a temporary focused mini-knowledge-base for a particular topic that I then load into an LLM for voice-mode interaction on a long 7-10 mile run. So it becomes an interactive podcast while I run."*
→ `kb_export_subset <topic> --format=voice` emits a topic-scoped slice (sub-wiki) loadable into voice LLMs or mobile clients.

**B3. JupyterBook HTML reports.** Pre-rendered, mobile-friendly, lecture-note feel — good for long-form synthesis output.

**B4. AI-agent-consumable outputs (Pratiyush / llm-wiki).** Dual-format output per page: `.html` + `.txt` + `.json` siblings + `/llms.txt`, `/llms-full.txt`, `/graph.jsonld`, `/sitemap.xml`, `/robots.txt` for AI-agent consumption.
→ **The wiki itself becomes a retrievable source for other agents.** Low effort: generate alongside existing markdown.

**B5. k-topic combinatorial synthesis (Elvis Saravia).** *"You can synthesize any k number of topics across any k domains and the possibility becomes O(n^k). For a 500-note vault: k=2: 250,000 ordered pairs, k=3: 125 million paths, k=4: 62.5 billion. You can connect 'stoic philosophy' - 'saas pricing' - 'viral content' - 'parenting' and agent can actually traverse that path and find something coherent."*
→ `kb_synthesize [t1, t2, t3]` explicitly walks the k-tuple path and writes a synthesis page. Beyond normal retrieval — a new query mode.

---

### Theme C — Ingest patterns for novel source types

**C1. Session transcript auto-ingest (Pratiyush / llm-wiki).** Ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. *"Every conversation you've ever had with your agents."* `SessionStart` hook on every Claude Code launch + `llmwiki watch` file watcher with debounce.
→ **Zero-capture-cost.** The corpus already exists on disk. Our `kb_capture` idea is manual; this is ambient.

**C2. Staging directory for drop-and-forget (Ar9av / obsidian-wiki).** `_raw/` staging inside the vault for rough notes/clipboard pastes. Next `wiki-ingest` promotes and removes.
→ Complements `raw/`: staging is for unformed notes that need LLM structuring; `raw/` is for sourced documents.

**C3. Comprehensive adapter list (swarmvault).** `.eml`/`.mbox` (email), `.ics` (calendar), Slack export `.zip`, `.srt`/`.vtt` (transcripts), BibTeX, Org-mode, AsciiDoc, extensionless shebang scripts. Guided-ingest sessions staged under `wiki/outputs/source-sessions/` as resumable `source session <id>` objects.
→ Our `SOURCE_TYPES` set is narrow (articles, papers, repos, videos, podcasts, books, datasets, conversations). Email, calendar, Slack, transcripts, BibTeX, Org-mode would all be natural adds.

**C4. Per-subdir-rules ingest (Fabian Williams).** `raw/web/`, `raw/transcripts/`, `raw/papers/` each with type-aware ingest rules inferred from path. Simpler than an explicit `--type` flag.
→ Our ingest already routes by type but accepts explicit arg. Inferring from subdir makes the default argument-free.

**C5. Personal-life-corpus templates (anonymous personal-data-RAG reply).** Google Takeout (Gmail, Drive, YouTube, Maps), Apple Health, legal docs photographed, public records, bank statements, all AI session exports. *"How much did I spend on trading cards in 2022" / "How many kms did I walk in the last 3 months" / "What are the most common dumb mistakes I make while coding?"*
→ Not generic research KB — a **personal-life KB template** with privacy-aware ingest (C4 + `.llmwikiignore`).

---

### Theme D — Query quality & failure prevention

**D1. Coverage confidence score (VLSiddarth / Knowledge-Universe).** Average cosine similarity between query and top results; **<0.45 triggers a warning with LLM-suggested rephrased queries**. Refuses bad questions instead of synthesizing mediocre answers.
→ **Gap filled:** our `kb_query` always answers. Adding "I can't answer this confidently, did you mean ..." is a quality gate.

**D2. Per-platform decay half-lives (VLSiddarth).** HuggingFace 120d, GitHub 180d, StackOverflow 365d, arXiv 1095d, Wikipedia 1460d, OpenLibrary 1825d, with topic-volatility multiplier (LLM/React/Docker/Claude get ×1.1).
→ **Gap filled:** our stale-flagging is single-threshold. Source-platform-aware decay is more honest.

**D3. Duplicate-concept detection (Louis Wang).** Lint check for near-duplicate slugs (`attention` vs `attention-mechanism`). `/kb-merge <a> <b>` — LLM merges two pages, updates all backlinks across `wiki/` and `outputs/`, archives absorbed page to `wiki/archive/` with a redirect note, one git commit per merge.
→ **Gap filled:** we have slug-collision tracking but no merge command. `kb_merge` as first-class operation.

**D4. Two-stage `/kb-reflect` (Louis Wang).** Stage 1 discovers connection candidates from `index.md` alone (scan tier); Stage 2 deep-reads to write `type: synthesis` pages (write tier).
→ **Gap filled:** our `kb_evolve` is single-stage. Split cheap discovery from expensive synthesis.

**D5. Container boundary / atomic notes tension (WenHao Yu).** *"`kb_ingest` forces 'which page does this source merge into?' Same failure as Evernote's 'which folder' and Notion's 'which tag.' Atomic notes (one-concept-per-page) sidestep."*
→ **Design tension to name explicitly.** Our current model merges aggressively into existing entity/concept pages. An atomic-mode alternative (one claim → one page, heavy linking) is a different spot on the spectrum.

**D6. Mustafa Genc's three failure modes.** (1) error accumulation/drift, (2) partial context on update (LLM only sees a subset of docs), (3) information loss through compression.
→ **Map to test cases:** "ingest two sources back-to-back and verify the first source's nuance survives the second" is a regression test we don't have.

---

### Theme E — Graph & structural signals

**E1. 4-signal graph relevance weights (nashsu / llm_wiki).** Direct-link ×3, source-overlap ×4, Adamic-Adar ×1.5, type-affinity ×1. With ForceAtlas2 layout + sigma.js viz.
→ Concrete weight ratios for our deferred "multi-signal graph retrieval." `source-overlap` (pages sharing a raw source) is weighted highest — non-obvious and empirically tuned.

**E2. Louvain cohesion threshold (nashsu).** Intra-edge density per community; **<0.15 flagged as "sparse/weak."** Bridge nodes connecting 3+ communities surfaced as "high-value connection targets."
→ Quantitative threshold for our deferred community-boost and graph-topology-gap features.

**E3. Graph Insights card types (nashsu).** "Isolated pages (degree ≤ 1)," "Bridge nodes," "Sparse communities" — each a card type in a dashboard with one-click "Deep Research" trigger that dispatches `kb_evolve --research` on the specific gap.
→ UI pattern for our deferred `kb_evolve` upgrade.

**E4. Overview-mode graph rollup (swarmvault).** On large graphs, auto-enable "overview mode" that rolls up tiny fragmented communities for readability.
→ Scaling technique for the deferred interactive graph viewer itself.

---

### Theme F — Session lifecycle & ambient capture

**F1. SessionStart hook + file watcher (Pratiyush).** Auto-sync new sessions in the background on every Claude Code launch; `llmwiki watch` file watcher with debounce for `raw/` directory.
→ Removes the "remember to ingest" step entirely. Hooks into Claude Code's lifecycle.

**F2. Haiku-based watcher every 3 min + PreCompact gates (IlyaGorsky / Memory-Toolkit, from gist).** Continuous Haiku-tier watcher scans active context; human-confirmation gate before persistence.
→ Different trigger granularity than F1. F1 is file-system-driven; F2 is LLM-driven over conversation.

**F3. Session boundaries as events (rohitg00).** On-session-start: load relevant context from wiki based on recent activity. On-session-end: compress session into observations, file insights.
→ Expands our deferred `wiki/hot.md` with automatic triggers.

**F4. PAI LEARN phase (Daniel Miessler).** *"Anything we've been working on in a session gets harvested as a Knowledge article."* LEARN phase decides whether a session should be promoted to `MEMORY/KNOWLEDGE`.
→ Complements F3 with a decision gate: not every session promotes.

---

### Theme G — Multi-device & distribution

**G1. Hosted KB over MCP (Hjarni / dev.to).** KB exposed via MCP HTTP/SSE so phone Claude app, ChatGPT, Cursor, Claude Code all read/write the same brain.
→ Our MCP server is stdio-only. Adding an HTTP/SSE variant gives multi-device for cheap.

**G2. Embed mode (pdombroski / KIOSK, from gist).** `llm-wiki/` as drop-in folder inside any codebase. Project-scoped KB, not monolithic.
→ Different distribution model: embed mode vs. repo-as-wiki mode.

**G3. Scenario profile templates at init (nashsu).** `kb init --profile {research|reading|personal|business|general}` pre-configures `purpose.md` and schema.
→ Onboarding sugar; reduces blank-canvas paralysis.

---

### Theme H — Scaling beyond 200 pages

**H1. 100–200 page breakpoint for `index.md` (rohitg00).** *"index.md works up to maybe 100–200 pages. Beyond that, the index itself becomes too long for the LLM to read in one pass."*
→ Quantifies the ceiling we've been worried about. Strategy above the ceiling: hierarchical index (index-of-indexes), or compressed scan-tier summary of the full index.

**H2. Automaton Memory System / importance decay (plundrpunk, from gist).** At 200+ pages, compress low-importance stub pages into parent summary pages. Hierarchical memory.
→ Natural companion to H1.

**H3. Epsilla's "can never be enterprise" critique.** File-based KB: no RBAC, no compliance audit log, `zip -r` data-exfiltration risk, file-I/O can't hold millions of docs.
→ **Know-thy-ceiling** README section. Honest scope statement: this is personal-scale research, not enterprise.

**H4. Shumailov 2024 (Nature) — model collapse.** When LLM-written pages feed next LLM ingest, performance degrades across generations.
→ Counter: human-review-gated promotion (two-vault). Citation to add to CHANGELOG "known limitations."

---

## Prioritized roadmap additions

This section translates the novel material above into a concrete set of backlog items. Items are grouped by theme and labeled against the existing phase structure.

### New Phase 5 theme candidate: "Epistemic Integrity 2.0 + Multi-Format Output"

Eleven items that together raise trustworthiness and output flexibility without expanding scope beyond single-user research KB:

| # | Item | Source | Effort | Leverage |
|---|---|---|---|---|
| 1 | `belief_state: confirmed\|uncertain\|contradicted\|stale\|retracted` frontmatter | A (epistemic mapping) | Low | High |
| 2 | Subsection-level provenance (`source: raw/file.md#heading`) | A (Agent-Wiki) | Med | High |
| 3 | `authored_by: human\|llm\|hybrid` marker + asymmetric trust | A (PKM critique) | Low | Med |
| 4 | `kb_drift_audit` — cold re-ingest random sample, diff vs current | A (asakin) | Med | High |
| 5 | `kb_merge <a> <b>` + duplicate-slug lint check | D3 (Louis Wang) | Med | High |
| 6 | `kb_consolidate` — sleep-cycle background pass (NREM/REM/Pre-Wake) | A1 (Anda) | High | High |
| 7 | `kb_query --format={marp\|html\|chart\|jupyter}` output adapters | §1, B | Med | High |
| 8 | `kb_export_subset <topic> --format=voice` for mobile/voice LLMs | B2 | Low | Med |
| 9 | `/llms.txt` + `/graph.jsonld` auto-generation for agent consumption | B4 | Low | Med |
| 10 | `kb_query` coverage-confidence gate (<0.45 refuses with rephrase suggestions) | D1 | Low | High |
| 11 | `kb_synthesize [t1, t2, t3]` — k-topic combinatorial path synthesis | B5 | Med | Med |

### New Phase 5.5 theme candidate: "Ambient Capture + Session Integration"

Five items that automate the "remember to ingest" step:

| # | Item | Source | Effort | Leverage |
|---|---|---|---|---|
| 12 | Session transcript auto-ingest (Claude Code/Codex/Cursor JSONL) | C1 | Med | High |
| 13 | SessionStart hook + `raw/` file watcher with debounce | F1 | Low | Med |
| 14 | `_raw/` staging directory for clipboard/drop-and-forget | C2 | Low | Med |
| 15 | `.llmwikiignore` + secret-scanning pre-ingest filter | A4 | Low | High |
| 16 | Per-subdir ingest rules inferred from path (no `--type` arg needed) | C4 | Low | Low |

### Deferred-list refinements (add specifics already agreed in principle)

Items already in Phase 5/6 deferred but where the community surfaced concrete numbers or UX patterns worth capturing:

- **Multi-signal graph retrieval weights** → use nashsu's empirical 3/4/1.5/1 ratios (direct / source-overlap / Adamic-Adar / type-affinity).
- **Community-aware retrieval boost** → threshold Louvain cohesion at <0.15 for "sparse/weak" flagging (E2).
- **Stale flagging at query time** → source-platform-aware decay half-lives (HF 120d, GitHub 180d, SO 365d, arXiv 1095d, Wikipedia 1460d) rather than single threshold (D2).
- **Context budget** → 60/20/5/15 split (wiki pages / chat history / index / system) instead of single `CONTEXT_TIER1_BUDGET` (nashsu).
- **Evolve `mode=research`** → expose "Graph Insights" card types (isolated / bridge / sparse-community) with one-click trigger (E3).
- **Page status lifecycle** → use rohitg00's memory-tier taxonomy (Working/Episodic/Semantic/Procedural) as the naming convention.
- **Interactive knowledge graph HTML viewer** → include overview-mode rollup for large graphs (E4) and 3-column streaming UI (nashsu).

### New Phase 6+ additions

- **Sleep-cycle consolidation** scheduled as a cron (cheap scan-tier nightly pass).
- **Hermes-style independent quality-gate supervisor** — different model family validates before promotion (A6).
- **Mesh sync for multi-agent writes** — last-write-wins with private/shared scoping (rohitg00).
- **Hosted KB over MCP HTTP/SSE** for multi-device access (G1).
- **Personal-life-corpus templates** (Google Takeout + Apple Health + AI session exports) as a domain starter kit (C5).

---

## Explicitly evaluated, not adopted

| Pattern | Source | Why skip |
|---|---|---|
| Cloud-hosted `secondbrain.com` multiplayer | @someoneuk reply | Conflicts with local-first, git-tracked, file-based intent |
| Full OWL-RL + SPARQL deterministic reasoning | Cortex (gist) | Over-engineered for single-user; typed wikilinks already approximate |
| Ed25519-signed page receipts | tomjwxf (gist) | Single-user KB; git log already provides audit |
| Full RBAC + compliance audit log | Epsilla critique | Explicit non-goal; file-based KB has a ceiling and that's fine |
| RDF-Turtle/JSON-LD native storage | Grok knowledge-graph reply | Markdown + wikilinks + frontmatter cover the same semantic ground with human readability |
| Thick 3-column desktop UI as primary frontend | nashsu | Obsidian already fills this role; we stay CLI/MCP-first |
| Separate per-session "harvest" step | Daniel Miessler PAI | Overlaps with session-transcript auto-ingest (C1); choose C1 |
| Qwen-4B local tagging wrapper | @qwen_tag reply | Our tier split already covers cheap operations via Haiku |

---

## Recommended next step

If the user wants a single-phase pickup for Phase 5:

**Ship the 11-item "Epistemic Integrity 2.0 + Multi-Format Output" bundle.** It's the highest-leverage slice because:

1. Five items (#1–5) attack the unsolved problem every community voice flagged: epistemic contamination at scale.
2. Three items (#7–9) unlock Karpathy's own tweet-stated behaviors (Marp, charts, rendered HTML, AI-agent-consumable outputs) that our system currently can't produce.
3. Three items (#6, #10, #11) are novel enough to be differentiators (sleep-cycle consolidation, coverage-confidence gate, k-topic synthesis).
4. All eleven fit within the existing module layout (`kb.query`, `kb.lint`, `kb.ingest`, `kb.utils`) — no major restructuring.

If the user wants distribution/adoption work instead, pivot to the Phase 5.5 "Ambient Capture" bundle (#12–16) — shorter, narrower, produces immediate UX wins.

---

## Sources

### Primary
- [Karpathy's original X post](https://xcancel.com/karpathy/status/2039805659525644595) — full tweet text retrieved Apr 12, 2026
- [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — original gist + comments
- [VentureBeat coverage](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)

### Community forks / implementations (not already in existing research files)
- [ICPandaDAO/anda-hippocampus](https://github.com/ldclabs/anda-hippocampus) — sleep-cycle consolidation
- [rohitg00/llm-wiki-v2 gist](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) — Ebbinghaus decay, memory tiers
- [Pratiyush/llm-wiki](https://github.com/Pratiyush/llm-wiki) — SessionStart hooks, /llms.txt
- [Ar9av/obsidian-wiki](https://github.com/Ar9av/obsidian-wiki) — `_raw/` staging
- [swarmclawai/swarmvault](https://github.com/swarmclawai/swarmvault) — 50+ format adapters
- [lewislulu/llm-wiki-skill](https://github.com/lewislulu/llm-wiki-skill) — anchored audit queue
- [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) — severity-tiered lint-as-pages
- [Lum1104/Understand-Anything](https://github.com/Lum1104/Understand-Anything) — persona-adaptive UI, /understand-diff
- [iamsashank09/llm-wiki-kit](https://github.com/iamsashank09/llm-wiki-kit) — YouTube transcript ingest
- [jhinpan FTS5 gist](https://gist.github.com/jhinpan/16f240dfce4b45532f28b5df829bc887) — raw-source lifecycle frontmatter

### Analytical posts / critiques
- [Louis Wang on LLM Knowledge Bases](https://louiswang524.github.io/blog/llm-knowledge-base/) — duplicate-slug lint, /kb-merge, /kb-reflect, security gap
- [Fabian Williams — Second Brain That Compounds](https://www.fabswill.com/blog/building-a-second-brain-that-compounds-karpathy-obsidian-claude) — Marp/chart output CLI, git commit receipts
- [WenHao Yu — Karpathy vs Zettelkasten](https://yu-wenhao.com/en/blog/karpathy-zettelkasten-comparison/) — container boundary tension
- [Hjarni on dev.to — hosted KB over MCP](https://dev.to/hjarni/karpathys-llm-wiki-is-right-i-just-didnt-want-to-run-it-locally-170m)
- [VLSiddarth Knowledge-Universe](https://dev.to/vlsiddarth/andrej-karpathy-said-manual-data-ingest-for-ai-agents-is-too-slow-i-built-the-fix-2co8) — per-platform decay, coverage confidence
- [Epsilla enterprise critique](https://www.epsilla.com/blogs/llm-wiki-kills-rag-karpathy-enterprise-semantic-graph) — file-based KB ceiling
- [Mustafa Genc on Medium](https://medium.com/data-science-in-your-pocket/andrej-karpathys-llm-wiki-bye-bye-rag-ee27730251f7) — three failure modes
- [Lobster Pack coverage](https://www.lobsterpack.com/blog/karpathy-llm-wiki-idea-files/) — image-aware ingest gap
- [HN thread](https://news.ycombinator.com/item?id=47493938) — vibe-thinking critique
- [DAIR.AI — LLM Knowledge Bases](https://academy.dair.ai/blog/llm-knowledge-bases-karpathy)

### Context from existing research files (not re-listed)
- `research/karpathy-llm-knowledge-bases-analysis.md`
- `research/gbrain-analysis.md`
- `research/project-ideas.md`
- `research/agent-architecture-research.md`
- `research/tooling-research.md`
- `research/mcp-servers-research.md`
