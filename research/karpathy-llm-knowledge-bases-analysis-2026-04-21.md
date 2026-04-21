# Karpathy LLM Knowledge Bases: April 21 Research Refresh

*Newer version of [karpathy-llm-knowledge-bases-analysis.md](karpathy-llm-knowledge-bases-analysis.md). Researched 2026-04-21, focused on comments and implementations after the original 2026-04-05 analysis and after the 2026-04-12/13 follow-up passes.*

---

## Executive Read

The April 12 and April 13 research files already captured the first wave: output adapters, lint augmentation, machine-consumable exports, `AGENTS.md`, `belief_state`, coverage-confidence refusal, `.llmwikiignore`, session capture, and watcher/staging flows. Several of those have now shipped locally or are already tracked in `BACKLOG.md`.

The newer April 14-21 signal is different. It is less about copying Karpathy's loop and more about hardening the missing middle:

1. **Claim-level source of truth** — add an atom/proof layer between `raw/` and `wiki/`; treat wiki pages as rebuildable views, not ground truth.
2. **Deterministic relation capture** — LLMs cannot infer hidden personal context from unlabeled files; humans need a fast way to assert stable labels, people, projects, evidence sets, and relationships at ingest time.
3. **Validation states and locked regions** — pages or claims should move through `unreviewed -> pending_validation -> validated`, and validated content should become harder for the LLM to rewrite casually.
4. **Scale modes** — pure index scans and Obsidian graphs strain around hundreds to low-thousands of pages; large deployments need hybrid search, hierarchical indexes, and explicit corpus limits.
5. **Human navigation/stewardship** — a pile of markdown files is not enough. Mature wikis need curated entry points, ownership, review queues, and dashboards that let humans understand what the agent built.

The practical roadmap shift: the highest-value future work is no longer basic Karpathy fidelity. It is **epistemic infrastructure**: atoms, proofs, validation, deterministic labels, and scale-aware retrieval.

---

## What Changed Since The Earlier Research

### 1. The gist thread turned critical and more concrete

The newer visible GitHub gist comments are mostly April 17. The useful signal is not the tone; it is the failure cases.

One commenter reported a codebase wiki experiment at about **10k objects, 30 apps, and 200k edges**. Obsidian struggled, and agents with access to the wiki still produced underwhelming architectural answers. This strengthens the previous "100-200 pages" ceiling: beyond focused personal research scale, the system needs a real retrieval and graph strategy.

Another thread made a sharper point: an LLM cannot infer relationships that are not in the text. If a screenshot, phone number, or file has important human context that exists only in the user's head, the LLM cannot reliably connect it to the right person, case, project, or event. That argues for **human-in-the-loop relation stamping** at ingest time, not just LLM-generated wikilinks after the fact.

A more constructive defense framed Karpathy's pattern as a readable hypertext graph: the value is not "wiki" purity, it is a text-native graph that humans can inspect and correct. That same comment suggested validation states: unreviewed, pending validation, and validated regions that the LLM cannot freely rewrite.

### 2. Wiki practitioners pushed back on "automation replaces stewardship"

Andreas Gohr's DokuWiki newsletter, dated April 15, is the strongest post-original critique from an experienced wiki practitioner. The core claim: collecting information is not the same as creating knowledge. Karpathy's own supervised ingest style implies the human role has shifted from writer to architect/QA, not disappeared.

The critique also names a navigation problem: hundreds of markdown files plus `index.md` and graph view can become cognitively opaque. Traditional wiki value comes from human-designed paths, page titles, namespaces, ownership, summaries, and entry points. Without that editorial layer, the LLM may be able to search the corpus while humans lose confidence in it.

### 3. Implementations converged on missing architectural layers

The most important new repo is `cablate/llm-atomic-wiki`. Its addition is simple and high leverage:

`raw -> atoms -> wiki`

An atom is one claim with source metadata. Atoms become the source of truth; wiki pages become a compiled cache. If a wiki page is wrong, you repair the atom or proof, then rebuild the page. This directly addresses the two hardest problems in the original pattern: compression loss and false source-of-truth drift.

The same repo adds topic branches, deterministic lint before LLM lint, and a parallel-compile naming lock so multiple agents do not invent divergent slugs for the same concept.

`chum-mem` pushes the same direction but with a stronger proof model: atomic typed claims, authority classes, verification status, contradiction detection, supersession, and a belief gate that rejects model-generated prose unless user-confirmed or tool/repo-derived.

`MehmetGoekce/llm-wiki` adds a useful cache hierarchy: L1 memory auto-loaded every session for rules/gotchas/preferences, and L2 wiki loaded on demand for deep knowledge. This matters because some knowledge must be present before the agent makes its first move.

`Pratiyush/llm-wiki` confirms that earlier ideas have become implementation baseline: session transcript ingestion, redaction by default, `.llmwikiignore`, privacy-first local serving, dual human/agent exports, JSON-LD graph, sitemap, and `llms.txt`.

`AI-Context-OS` contributes adapter-first thinking: keep a neutral memory core and generate tool-specific artifacts like `claude.md`, `AGENTS.md`, `.cursorrules`, and `.windsurfrules`. That is cleaner than making any single agent schema canonical.

### 4. A large domain deployment clarifies scaling needs

Joon An's AI-for-biology LLM wiki guide reports a domain KB with **1,060 source summaries, 1,427 wiki pages, 25 categories, 8 interactive visualizations**, daily paper monitoring, and QMD MCP search at 2,500+ documents.

Two design lessons stand out:

- At that scale, QMD-style hybrid local search is not optional. Index scanning is no longer enough.
- The project uses a strict "papers only" rule for answers and forbids web search gap-fill for synthesis. This conflicts with Karpathy's lint augmentation idea, but it is the right tradeoff for scientific research. Gap-fill should be policy-driven by domain, not universal.

---

## De-Dupe Against Local State

The following items from the April 12/13 research are already shipped or explicitly tracked, so they should not be re-proposed as fresh roadmap:

| Item | Local status |
|---|---|
| `kb_query --format={markdown,marp,html,chart,jupyter}` | Shipped in `query.formats` |
| `kb_lint --augment` | Shipped in `lint.augment` |
| `/llms.txt`, `/llms-full.txt`, `/graph.jsonld`, siblings, sitemap | Shipped in `compile.publish` |
| `belief_state`, `authored_by`, `status` frontmatter | Shipped as optional epistemic fields |
| Coverage-confidence refusal gate | Shipped; LLM-suggested rephrases remain deferred |
| Machine-consumable outputs filtered by epistemic state | Shipped in publish builders |
| `.llmwikiignore`, `_raw/`, watcher/session hooks | Already backlog / feature work |
| Inline claim tags and grounding verification | Already backlog / Cycle 22 candidates |

That means the net-new roadmap should bias toward architecture and enforcement rather than more feature surfaces.

---

## High-Value Future Roadmap Items

### P0. Add A Claim Atom / Proof Layer

**Why it matters:** Wiki pages are currently both compiled artifact and effective source of truth. The newer implementations show that this is the wrong abstraction boundary. Pages should be rebuildable views over smaller durable claims.

**Shape:**

- Add `atoms/` or `.data/claims/` as a first-class layer.
- Each atom is one typed claim: `fact`, `decision`, `constraint`, `open_question`, `method`, `relationship`, `contradiction`, `summary_claim`.
- Required fields: `claim_id`, `source_ref`, `source_span` where possible, `authority_class`, `verification_status`, `created_at`, `supersedes`, `superseded_by`.
- Ingest writes atoms first; wiki compile groups atoms into pages.
- Wiki pages carry generated prose, but every paragraph or bullet maps back to atom IDs.

**Roadmap value:** Very high. This is the cleanest answer to persistent hallucination, compression loss, and "wiki page became false ground truth."

**Implementation note:** Do not rewrite the whole pipeline first. Start with a shadow atom store emitted during ingest, then add one page type that compiles from atoms.

### P0. Deterministic Human Relation Stamping At Ingest

**Why it matters:** The April 17 critique is correct on one narrow but important point: the LLM cannot know hidden human context. Personal and business documents often need labels that are not present in the content.

**Shape:**

- Add optional ingest metadata: `people`, `projects`, `cases`, `organizations`, `time_period`, `evidence_set`, `sensitivity`, `user_labels`.
- Provide a fast CLI/MCP preflight: "Before ingest, attach any known relations."
- Store human-stamped relations separately from LLM-inferred relations.
- Retrieval should rank human-stamped edges above inferred wikilinks.
- Lint should flag high-impact pages whose main relations are only model-inferred.

**Roadmap value:** Very high for personal-life, legal, customer, and project-memory corpora. Less important for clean academic-paper corpora.

### P0. Validation States And Write Locks For Trusted Knowledge

**Why it matters:** `belief_state` exists, but newer comments point to workflow states: unreviewed material should be easy for the LLM to revise; validated material should require explicit approval to change.

**Shape:**

- Add claim/page lifecycle: `draft`, `unreviewed`, `pending_validation`, `validated`, `deprecated`, `retracted`.
- `validated` claims require a refine/audit operation, not normal ingest overwrite.
- Lint can propose edits to validated content, but writes them to a review queue.
- `kb_query` can expose whether an answer rests on validated vs unreviewed claims.

**Roadmap value:** Very high. It turns epistemic fields from metadata into enforcement.

### P0. Hybrid Scale Mode With Hierarchical Indexes

**Why it matters:** The new large-scale examples clarify that the pure markdown/index approach has a real ceiling. At 1k+ pages and 2.5k+ docs, local hybrid search becomes part of the architecture.

**Shape:**

- Define scale tiers:
  - Tier A: under 200 pages, `index.md` and BM25 are enough.
  - Tier B: 200-2,000 pages, hierarchical indexes plus hybrid search.
  - Tier C: 2,000+ pages, required vector/BM25 index, graph summaries, and category indexes.
- Add `kb doctor scale` to report page count, index length, graph density, orphan count, and recommended mode.
- Add category/subgraph index files: `wiki/indexes/{category}.md`.
- Make QMD-like local search or the existing vector index a first-class required path above threshold.

**Roadmap value:** Very high. It prevents the architecture from over-promising.

### P1. Programmatic Lint Before LLM Lint

**Why it matters:** `llm-atomic-wiki` split lint into deterministic checks first and semantic checks second. That is the right cost and reliability boundary.

**Shape:**

- Ensure every formatting, frontmatter, dead-link, slug, duplicate, stale-source, and forbidden-rewrite check runs without LLM calls.
- Only then run semantic checks: contradiction, unsupported claims, missing nuance, weak synthesis.
- Emit separate sections: `deterministic_failures`, `semantic_risks`, `llm_suggestions`.

**Roadmap value:** High. It reduces token waste and makes lint output more trustworthy.

### P1. Naming Locks And Slug Registry For Parallel Compile

**Why it matters:** Parallel agents inventing different filenames for the same concept is now a documented implementation pain. The local code has already hardened some slug-collision paths, but a semantic slug registry is a different thing.

**Shape:**

- Maintain `.data/slug_registry.json` mapping canonical concept/entity IDs to slugs, aliases, and page paths.
- During batch/parallel compile, reserve slugs before content generation.
- Agents fill pre-named slots; they do not independently choose final filenames.
- `kb_merge` should update this registry and leave redirects.

**Roadmap value:** High, especially if session hooks and watchers make concurrent writes common.

### P1. Stewardship Dashboard / Human Navigation Layer

**Why it matters:** The DokuWiki critique is not solved by more graph edges. Humans need curated entry points and quality affordances.

**Shape:**

- Add generated but human-editable pages:
  - `wiki/home.md` — curated entry point.
  - `wiki/review_queue.md` — pending validation, low-confidence, contradicted, stale.
  - `wiki/map.md` — stable human-facing topic map, not just exhaustive index.
  - `wiki/ownership.md` — who/what owns high-value domains, even for single-user mode.
- Add dashboard metrics: validated coverage, unreviewed pages, inferred-only edges, stale claims, duplicate candidates.

**Roadmap value:** High. It makes the KB useful to read, not just useful for an agent to search.

### P1. Domain Policy Profiles

**Why it matters:** The biology guide uses "no web search, papers only"; Karpathy uses web search in lint; personal corpora need privacy gates. One policy will be wrong for at least one domain.

**Shape:**

- `kb init --profile research_papers|personal|business|codebase|legal|general`.
- Profiles configure:
  - whether lint can fetch web sources,
  - required source types,
  - minimum verification status for answers,
  - whether inferred claims can be saved,
  - retention and redaction behavior.

**Roadmap value:** High. It prevents "web gap-fill" from contaminating scientific or legal KBs while preserving it for exploratory research.

### P2. L1/L2 Memory Hierarchy

**Why it matters:** Some knowledge must be auto-loaded before the agent can safely operate: rules, preferences, active hazards, credentials policy, project gotchas. A query-only wiki is too late for those.

**Shape:**

- L1: compact, auto-loaded memory files for standing rules and safety-critical facts.
- L2: full wiki, searched on demand.
- Lint checks for duplicates and contradictions between L1 and L2.
- Promote/demote commands: `kb promote-to-l1`, `kb demote-from-l1`.

**Roadmap value:** Medium-high. It is most useful for coding-agent memory and operations KBs.

### P2. Domain Monitors And Source Acquisition Pipelines

**Why it matters:** The biology wiki's daily monitor is a concrete high-value workflow: search sources, score relevance, produce an ingest-ready report, then let the human choose.

**Shape:**

- `kb monitor` framework with pluggable sources: arXiv, bioRxiv, PubMed, GitHub releases, RSS, Hacker News, internal docs.
- Each monitor writes `research/monitor_reports/YYYY-MM-DD.md` or `wiki/source_candidates/YYYY-MM-DD.md`.
- Candidate states: `auto_ingest_ready`, `manual_review`, `rejected`, `deferred`.

**Roadmap value:** Medium-high. It creates a source flywheel without pretending all acquisition should be automatic.

### P2. Local Web IDE / Browse Surface

**Why it matters:** Multiple newer implementations converged on web or desktop UIs. Obsidian is powerful, but it is not the whole product surface if the KB needs review queues, validation states, provenance panes, and relation stamping.

**Shape:**

- Three-pane app: source/atom, compiled page, graph/provenance.
- Review actions: validate, reject, supersede, lock, merge, attach relation.
- Local-only by default, optional MCP HTTP bridge.

**Roadmap value:** Medium. Valuable once atoms/proofs exist; premature before that.

---

## Updated Priority Recommendation

If choosing one new phase after the current epistemic hardening work:

**Ship "Claim Atoms + Validation Enforcement" before expanding product surfaces.**

Suggested slice:

1. Shadow atom store emitted by ingest.
2. Atom IDs referenced from generated wiki page evidence trails.
3. `verification_status` and `authority_class` on atoms.
4. Lint rule: wiki claims without atom/proof backing are flagged.
5. Page/claim lifecycle enforcement for `validated` content.
6. Minimal CLI/MCP review queue for validate/retract/supersede.

This phase directly answers the strongest post-original critiques and composes with shipped features: publish filters, `belief_state`, query refusal, lint augment, and output adapters all become more reliable when their substrate is claim/proof based.

The second phase should be **Deterministic Relations + Scale Mode**:

1. Human-stamped ingest relations.
2. Slug registry and alias map.
3. Hierarchical indexes.
4. Scale doctor.
5. Hybrid-search-required threshold.

That phase answers the hidden-context and large-corpus critiques.

---

## Explicitly Not Recommended Yet

| Idea | Reason |
|---|---|
| Full enterprise RBAC/compliance | Still conflicts with local-first personal research scope; document ceiling instead. |
| Database-first rewrite | Atoms/proofs can be file-backed first. Move to SQLite/Postgres only after the data model proves itself. |
| Fully autonomous web gap-fill | Domain profiles should gate this; "papers only" research corpora should reject it. |
| More output formats | Existing adapters and publish formats are enough for now. Trust substrate is the bottleneck. |
| Multi-agent swarm orchestration | Naming locks and proof/validation should come first; otherwise swarms amplify inconsistency. |
| Synthetic fine-tuning | Still over the horizon until the compiled corpus has strong provenance and validation. |

---

## Sources

Primary:

- [Karpathy GitHub gist: llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [XCancel mirror of Karpathy's X post](https://xcancel.com/karpathy/status/2039805659525644595)

Post-original / newer community signal:

- [cablate/llm-atomic-wiki](https://github.com/cablate/llm-atomic-wiki)
- [kimsiwon-osifa7878/mnemovault](https://github.com/kimsiwon-osifa7878/mnemovault)
- [sly-codechum/chum-mem](https://github.com/sly-codechum/chum-mem)
- [alexdcd/AI-Context-OS](https://github.com/alexdcd/AI-Context-OS)
- [MehmetGoekce/llm-wiki](https://github.com/MehmetGoekce/llm-wiki)
- [Pratiyush/llm-wiki](https://github.com/Pratiyush/llm-wiki)
- [Joon An: LLM Wiki for AI in Biology](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)
- [Andreas Gohr / CosmoCode: Thoughts on LLM Wikis](https://www.cosmocode.de/en/services/wiki/dokuwiki-newsletter/2026-04-15/)
- [Mehul Gupta: Andrej Karpathy's LLM Wiki is a Bad Idea](https://medium.com/data-science-in-your-pocket/andrej-karpathys-llm-wiki-is-a-bad-idea-8c7e8953c618)

Local context:

- [karpathy-community-followup-2026-04-12.md](karpathy-community-followup-2026-04-12.md)
- [karpathy-community-followup-2026-04-13.md](karpathy-community-followup-2026-04-13.md)
- [BACKLOG.md](../BACKLOG.md)
- [CLAUDE.md](../CLAUDE.md)
