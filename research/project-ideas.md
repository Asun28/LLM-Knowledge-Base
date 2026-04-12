# Project Ideas for llm-wiki-flywheel

Ideas distilled from Karpathy's pattern, community reactions, and gaps nobody has filled yet.

---

## Idea 1: Epistemic Layer (the missing piece)

Nobody has built proper "unit tests for knowledge." Add an epistemic metadata layer:

- Every wiki claim gets a `source:` backlink, a `confidence:` level (stated/inferred/speculative), and a `last_verified:` date
- A `contradictions.md` page that explicitly tracks conflicting claims across sources rather than silently resolving them
- A `drift detector` — re-ingest a source and diff the wiki output against what's already there. If they diverge, something drifted
- Idempotency checks: ingesting the same source twice should produce zero wiki changes

This is the gap everyone identifies but nobody ships. First to solve it wins.

---

## Idea 2: Two-Vault Architecture (Kepano's insight, productized)

Implement Kepano's vault separation as a first-class feature:

```
raw/            ← immutable sources (human-curated)
wiki/draft/     ← LLM-compiled content (messy vault)
wiki/promoted/  ← human-reviewed, promoted content (clean vault)
```

Promotion workflow: LLM compiles into `draft/`, human reviews and promotes to `promoted/` with a single command. `promoted/` pages get a `reviewed_by:` and `promoted_date:` in frontmatter. Queries prefer `promoted/` but fall back to `draft/`.

This gives you both speed (LLM does the work) and trust (human verifies what matters).

---

## Idea 3: Multi-Source-Type Templates (inspired by Mnemon)

Different source types need different extraction strategies:

| Source Type | What to Extract |
|---|---|
| **Research paper** | Abstract, key claims, methodology, results, limitations, citations |
| **Article/blog post** | Core argument, evidence, author credentials, publication date |
| **YouTube video** | Transcript → key points, timestamps for claims, speaker identity |
| **Podcast** | Speaker-attributed claims, topics by timestamp, action items |
| **GitHub repo** | Architecture, key abstractions, dependencies, what problem it solves |
| **Dataset** | Schema, size, provenance, known biases, example records |
| **Book chapter** | Characters/entities, themes, key arguments, quotes with page numbers |
| **Conversation/interview** | Speaker-attributed claims, agreements, disagreements, open questions |

Each template produces standardized frontmatter so the wiki layer can cross-reference uniformly.

---

## Idea 4: Compile-Time "Type Checking"

Borrow from programming: just as a compiler catches type errors before runtime, the lint pass should catch knowledge errors before they propagate:

- **Orphan detection** — Wiki pages with no backlinks (disconnected knowledge)
- **Dead link detection** — References to raw sources that were deleted or moved
- **Staleness scoring** — Pages that haven't been updated despite new related sources being ingested
- **Circular reasoning detection** — Page A cites Page B which cites Page A with no raw source anchor
- **Coverage gaps** — Raw sources that were ingested but produced suspiciously few wiki updates

Run these as a `lint` command that produces a report, not silent fixes.

---

## Idea 5: Query Feedback Loop with Provenance

When you query the wiki and get an answer:

1. The answer includes inline citations to specific wiki pages and raw sources
2. You can rate the answer (useful / wrong / incomplete)
3. Good answers get filed back as new wiki pages with `generated_from: query` metadata
4. Wrong answers trigger a review of the cited pages
5. Over time, you build a map of which wiki pages are reliable vs. which need attention

This turns every query into a quality signal.

---

## Idea 6: Differential Compilation (performance)

Currently: ingest a new source → LLM re-reads everything and updates ~10-15 pages.

Better: track what changed. When a new source is ingested:

1. LLM reads the new source + the index (not the entire wiki)
2. Identifies which existing pages are affected
3. Reads only those pages
4. Proposes diffs (not full rewrites)
5. Human or supervisor model approves

This cuts token cost dramatically and makes changes auditable via git diff.

---

## Idea 7: Personal LLM Fine-Tuning Pipeline

Karpathy's stated endgame: use the compiled wiki to generate synthetic training data and fine-tune a personal model. Build the pipeline:

1. Wiki pages → question-answer pairs (synthetic dataset generation)
2. Raw sources → ground truth for validation
3. Fine-tune a small model (e.g., Haiku-class) on your domain
4. The fine-tuned model handles routine queries cheaply
5. Frontier model (Opus-class) handles compilation and complex synthesis

Your wiki becomes both a knowledge base and a training corpus.

---

## Idea 8: Inter-Agent Gist Protocol

From the community: use GitHub gists as communication between different AI agents. Formalize this:

- Standardized gist format: frontmatter with `agent_source:`, `context:`, `request:`
- SVG diagrams and markdown context for visual reasoning
- Pass gists between Claude Code, Grok, GPT for multi-perspective analysis
- Merge agent outputs back into the wiki with attribution

This turns a single-agent workflow into a multi-agent research team.

---

## Idea 9: Domain-Specific Starter Kits

Package the pattern for specific use cases with pre-built schemas:

- **Research domain** — Paper tracking, citation graphs, methodology comparisons
- **Competitive analysis** — Company profiles, product comparisons, market maps
- **Book club / reading** — Character tracking, theme evolution, cross-book connections
- **Health / fitness** — Protocol tracking, biomarker trends, study summaries
- **Investment research** — Company fundamentals, thesis tracking, risk registers

Each kit includes: schema file, source templates, example lint rules, sample queries.

---

## Idea 10: Live Dashboard / Obsidian Plugin

Build a companion view that shows wiki health at a glance:

- Total sources ingested, pages compiled, queries answered
- Knowledge graph visualization (Obsidian's graph view, enhanced)
- Staleness heatmap (which areas haven't been updated)
- Contradiction count and unresolved flags
- Coverage score (% of raw sources fully integrated)
- Recent activity log

This makes the invisible "compile" work visible and trustworthy.

---

## What I'd Build First

If starting from scratch, the highest-leverage order:

1. **Basic three-layer structure** (raw/ + wiki/ + CLAUDE.md schema) — get the cycle working
2. **Multi-source-type templates** (Idea 3) — makes ingestion consistent and high-quality
3. **Epistemic metadata** (Idea 1) — solve the trust problem early before the wiki grows
4. **Compile-time lint** (Idea 4) — catch errors before they compound
5. **Two-vault promotion** (Idea 2) — add once you have enough content to need quality tiers

Everything else layers on top once the core cycle is solid.
