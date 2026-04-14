# Karpathy Gist Re-evaluation: 2026-04-13 Prioritized Sprint

*Researched 2026-04-13. Builds on [research/karpathy-community-followup-2026-04-12.md](karpathy-community-followup-2026-04-12.md) (yesterday's net-new distillation). Today's pass re-reads the gist, scans the post-Apr-12 comment thread, ranks against current state (v0.10.0 shipped; `wiki/purpose.md` shipped today as commit `d505dca`; `kb_capture` design spec landed today as commit `2a25535`), and produces a sequenced top-10 sprint plan.*

---

## What this doc adds over 2026-04-12

Yesterday's followup absorbed the gist, the X thread, the HN thread, 12+ community forks, and several critical blog posts. It produced a 50+ item unranked proposal pool keyed by theme and leverage. Today's doc does three things that file does not:

1. **Ranks the pool into a 10-item sequenced sprint** (Tier 1 / 2 / 3) rather than leveraging-by-theme.
2. **Records a post-Apr-12 comment-thread scan** and the finding that no new technical signal has appeared in the 24-hour window — evidence that the backlog is saturated and the bottleneck is now prioritization, not research.
3. **Records explicit scope-out decisions** with rationale, so future passes don't re-propose the same deferred items without new information.

The sequenced sprint has been written into `BACKLOG.md §Phase 5 → "RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13)"` and a one-paragraph pointer lives in `CLAUDE.md` above the Phase 5 prose. This doc is the narrative companion.

---

## Post-Apr-12 comment-thread scan

**Gist** (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — 23 new comments in the 2026-04-12 → 2026-04-13 window. Recurring handles (skyllwt / OmegaWiki, redmizt / multi-agent toolkit, KarabutRom / typed filenames, n7-ved / 4-claim epistemology, FBoschman / FUNGI, SonicBotMan / wiki-kb + Entity Registry) all posted material already summarized in the 2026-04-12 followup.

Net-new handles in the window with actionable content: **none**. Two newer handles (@sovahc, @RonanCodes) contributed observational or question-style replies without concrete proposals. A third (@joshwand) contributed a statistical critique — ~90% of comments LLM-written — which is meta-commentary, not a technique.

**Hacker News** (https://news.ycombinator.com/item?id=47493938) — no post-Apr-12 activity in the thread referenced by the 2026-04-12 followup.

**Conclusion.** The 48-hour-old research pool is effectively saturated. No idea has emerged in the window that would displace an item already on `BACKLOG.md`. Work should shift from discovery to delivery.

---

## Today's sequenced sprint (the 10-item recommendation)

Ranked by three axes applied against current code state:

1. **Karpathy-verbatim fidelity** — is this behavior a direct quote from his tweet?
2. **Unsolved-gap coverage** — does it close the "organized but not necessarily true" problem the community flagged?
3. **Effort vs. leverage** — low-effort high-leverage wins beat ambitious restructurings.

Items already in flight (`kb_capture`, `wiki/purpose.md`) are excluded from the ranking.

### Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce

| # | Item | Gist source quote | Effort | Why it's #1-tier |
|---|---|---|---|---|
| 1 | `kb_query --format={text\|marp\|html\|chart\|jupyter}` | *"render markdown files, slide shows (Marp format), matplotlib images"* | Medium | Karpathy's second-most-cited daily behavior. Lives inside `kb.query` — no schema migration, no new storage. Snapshot-testable per adapter. Largest user-visible payoff. Every subsequent item benefits from having richer output surfaces to render into. |
| 2 | `kb_lint --augment` (gap-fill via fetch MCP) | *"impute missing data (with web searchers), find interesting connections"* | Medium | Lint currently REPORTS gaps but doesn't FILL them. Distinct from deferred `kb_evolve mode=research` (proactive) — this is reactive to concrete lint findings. Closes the evolve → acquire → reingest loop with a single command. |
| 3 | `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen | Pratiyush/llm-wiki | Low | Makes the wiki itself a retrievable source for other agents. Renderers over existing frontmatter + graph — no new infra. Free distribution win. |
| 4 | `wiki/_schema.md` + `AGENTS.md` thin shim | Karpathy: *"schema is kept up to date in AGENTS.md"* | Medium | Vendor-neutral portable schema (Codex, Cursor, Gemini CLI, Droid all read `AGENTS.md`). The `BACKLOG.md` entry already specifies the innovation vs. naive symlink: schema lives with the data it describes, validated by lint, vendor shims stay ~10 lines. |

### Tier 2 — Epistemic integrity (unsolved-gap closers)

| # | Item | Source | Effort | Why it's #2-tier |
|---|---|---|---|---|
| 5 | `belief_state: confirmed\|uncertain\|contradicted\|stale\|retracted` frontmatter | dangleh (gist) | Low | Cross-source aggregate orthogonal to per-source `confidence`. One field + propagation rules in lint and ranking. Compounds with every future query. |
| 6 | `kb_merge <a> <b>` + duplicate-slug lint | Louis Wang | Medium | We have slug-collision tracking but no merge command. Catches `attention` vs `attention-mechanism` drift — the top-cited contamination failure mode in the thread. |
| 7 | Coverage-confidence refusal gate on `kb_query` | VLSiddarth | Low | Refuses low-signal queries with rephrase suggestions instead of synthesizing mediocre answers. One threshold check after existing hybrid search. |
| 8 | Inline `[EXTRACTED]` / `[INFERRED]` / `[AMBIGUOUS]` claim tags | llm-wiki-skill + n7-ved | Medium | Complements page-level `confidence` with claim-level provenance; `kb_lint_deep` spot-verifies a sample against raw source text. Directly answers "LLM stated this as sourced fact but it's not in the source." |

### Tier 3 — Ambient capture + security rail

| # | Item | Source | Effort | Why it's #3-tier |
|---|---|---|---|---|
| 9 | `.llmwikiignore` + pre-ingest secret/PII scanner | rohitg00 + Louis Wang | Low | Missing safety rail. Every ingest currently ships full content to the API with no regex filter. Unambiguously positive, low effort, no downsides. |
| 10 | `SessionStart` hook + `raw/` file watcher + `_raw/` staging | Pratiyush + Ar9av | Low each | Ship as a three-item bundle. `_raw/` handles clipboard paste; watcher handles drop-and-forget; hook handles session boundaries. Together they eliminate the "remember to ingest" step. |

### Recommended first target

**Item #1** (`kb_query --format={marp|html|chart|jupyter}`). Four reasons:

1. **Highest Karpathy fidelity.** Reproduces his #2 most-cited daily behavior. Defensible answer to "can your project do what Karpathy says he does?"
2. **Largest user-visible payoff.** Every downstream item (gap-fill reports, search results, coverage warnings) benefits from having richer surfaces.
3. **Contained blast radius.** Lives inside `kb.query`; no schema migration, no new storage, no cross-module surgery.
4. **Test easy.** Snapshot-test each adapter's file output. No flaky LLM asserts.

---

## Explicit scope-out decisions (today's pass)

These are in the 2026-04-12 pool but I recommend declining or deferring. Recorded here so future research passes don't re-propose them without new information.

| Pattern | Source | Decision | Rationale |
|---|---|---|---|
| `kb_consolidate` sleep-cycle pass (NREM/REM/Pre-Wake) | Anda Hippocampus | **Defer to Phase 6** | High effort (three sub-passes). Overlaps with existing lint/evolve. Defer until lint is load-bearing enough to warrant nightly automation. |
| Hermes-style independent cross-family supervisor | Secondmate via VentureBeat | **Defer to Phase 6** | Requires a second provider and a fail-open policy. Valuable but infra-heavy. Ship only after Tier 1–2 compounds usage signal. |
| `kb_drift_audit` cold re-ingest diff | asakin (gist) | **Defer** | Surface overlaps with `kb_merge` + `belief_state`. Revisit after those land; a contamination incident would be the natural trigger. |
| `kb_synthesize [t1, t2, t3]` k-topic combinatorial | Elvis Saravia | **Defer** | Speculative. Defer until everyday retrieval is saturated enough to reveal the k≥3 cross-domain use case. |
| `kb_export_subset --format=voice` | Lex-style reply | **Defer** | Niche (mobile/voice LLMs). Defer until a second-device need emerges. |
| Multi-agent swarm + YYYYMMDDNN naming + capability tokens | redmizt | **Decline** | Team-scale pattern. Explicit single-user local-first non-goal. |
| RDF / OWL / SPARQL native storage | Cortex + Grok-KG reply | **Decline** | Markdown + frontmatter + wikilinks cover the semantic surface. Human readability outweighs formal reasoning for single-user research. |
| Ed25519-signed page receipts | tomjwxf (gist) | **Decline** | Git log is the audit log at single-user scale. |
| Full RBAC / compliance audit log | Epsilla critique | **Decline** | Known and acknowledged ceiling. Document as a README limitation rather than attempt to fix. |
| Hosted multiplayer KB over MCP HTTP/SSE | Hjarni (dev.to) | **Decline** | Conflicts with local-first intent. Revisit only if a phone-access need emerges. |
| `qmd` CLI external dependency | Karpathy | **Decline** | In-process BM25 + vector + RRF already ships; adding an external tool duplicates capability. |
| Artifact-only lightweight alternative | freakyfractal | **Decline** | Sacrifices the persistence that is the whole reason this project exists. |
| FUNGI 5-stage rigid runtime framework | FBoschman | **Decline as runtime step** | Same quality gain expected from already-deferred two-step CoT ingest. |
| Synthetic fine-tuning on compiled wiki | Karpathy (endgame) | **Decline / over horizon** | Revisit only after stable, large-scale usage demonstrates the corpus is worth baking into weights. |

---

## Pointers

- **Authoritative sequenced list:** `BACKLOG.md §Phase 5 → "RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13)"`.
- **High-level pointer:** `CLAUDE.md` "Next sprint" paragraph above Phase 5 prose.
- **Yesterday's full distillation:** [research/karpathy-community-followup-2026-04-12.md](karpathy-community-followup-2026-04-12.md).
- **Original big-picture thesis:** [research/karpathy-llm-knowledge-bases-analysis.md](karpathy-llm-knowledge-bases-analysis.md).
- **Karpathy gist:** https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f.

---

## Sources

### Primary (re-verified today)
- Karpathy gist comment thread, 2026-04-12 → 2026-04-13 window (23 new comments, no net-new technical signal beyond the 2026-04-12 pool).
- `BACKLOG.md` Phase 5 section as of 2026-04-13 (post-commits `d505dca` and `2a25535`).

### Context (unchanged from 2026-04-12)
- All sources listed in `research/karpathy-community-followup-2026-04-12.md §Sources` — re-used without modification; no new citations warranted by today's scan.
