# LLM Knowledge Bases: Analysis of Karpathy's Pattern

*Based on Andrej Karpathy's [X post](https://x.com/karpathy/status/2039805659525644595) (April 3, 2026) and [GitHub gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (April 4, 2026)*

---

## What Karpathy Is Proposing

Karpathy revealed that a large fraction of his recent token throughput goes into manipulating knowledge — not code. The workflow: dump raw sources (papers, articles, repos, datasets, images) into a `raw/` directory, then have an LLM incrementally "compile" them into an interlinked markdown wiki. He queries the wiki with LLM agents, and files answers back in — so the knowledge base grows from use.

The system has three layers:

- **Raw sources** — Immutable curated documents. The LLM reads but never modifies.
- **The wiki** — LLM-generated markdown: summaries, entity pages, concept pages, comparisons, synthesis. The LLM owns this layer completely.
- **The schema** — A configuration document (CLAUDE.md or AGENTS.md) defining structure, conventions, and workflows.

And four operations in a cycle: **Ingest → Compile → Query → Lint**, then back to Ingest.

At his current scale (~100 articles, ~400K words), no vector database or RAG pipeline is needed. Structured markdown with LLM-maintained indexes is simpler, more transparent, and more debuggable.

---

## Why This Works

**Compile, don't search.** The core insight is the difference between retrieval and compilation. RAG is like `grep` — you search fragments at runtime. Karpathy's approach is like `gcc` — you pre-process into a structured artifact. The compiled wiki *is* the product, not an intermediate step. Cross-references and contradictions are already processed before you ask a question. It's the difference between grep and a textbook.

**Markdown as universal interface.** By treating `.md` files as the source of truth, you get human readability, git version control, Obsidian visualization, and LLM compatibility simultaneously. No embeddings, no black boxes. Every claim traces to a specific file a human can read, edit, or delete.

**LLMs solve the maintenance bottleneck.** This is the deepest point. Wikis have always been great in theory but die because humans won't maintain cross-references across 50 pages after adding one source. LLMs don't get bored, don't abandon projects, don't forget updates, and don't hesitate to touch multiple files simultaneously. The maintenance cost drops to near-zero. As Karpathy notes, this echoes Vannevar Bush's 1945 Memex concept — Bush couldn't solve maintenance; LLMs do.

**Knowledge compounds from use.** Every query, visualization, and answered question gets filed back into the wiki. The knowledge base doesn't just store — it grows. Good answers become new wiki pages. This creates a flywheel that traditional note-taking can't match.

---

## What the Community Built

The post went viral. Within 48 hours, the gist had dozens of implementations:

| Project | What It Does |
|---|---|
| **[rvk7895/llm-knowledge-bases](https://github.com/rvk7895/llm-knowledge-bases)** | Claude Code plugin implementing the full compile/query/lint cycle for Obsidian |
| **Mnemon** | Extraction pipeline with 7 source-type templates (article, video, podcast, book, paper, idea, conversation) |
| **Veritas Acta** | Multi-model verification with cryptographic receipts and zero-trust validation |
| **Obsidian Seed** | Discovery-driven wizard that builds personalized vaults through conversation |
| **Obsidian Skills** (by Kepano) | Teaches AI agents to work with Obsidian's native formats: `[[wikilinks]]`, callouts, Bases, Canvas |
| **Vibe Sensei** | Trading terminal integration for real-time market analysis |
| **Binder** | Transaction logs + SQLite indexing for structured data rendering |
| **The `.brain` folder pattern** | Lightweight alternative: `.brain/` at project root, read before changes, updated after, never committed to git |

This velocity of community response shows the idea has real legs beyond theory.

---

## Notable Voices

**Steph Ango (Kepano, Obsidian CEO)** — Proposed **vault separation**: keep your personal vault clean and high signal-to-noise with known content origins. Create a separate "messy vault" for agent-generated content. Only promote artifacts once verified. This mirrors the production vs. staging environment pattern in software — and it's the most practical architectural advice anyone offered.

**Vamshi Reddy** — *"Every business has a raw/ directory. Nobody's ever compiled it. That's the product."* Karpathy agreed, calling this an "incredible new product" category. This is the commercial insight: the value isn't in the raw data or the LLM — it's in the compiled, maintained wiki sitting between them.

**Elvis Saravia (DAIR.AI)** — Confirmed the pattern from his own experience. Shared his complementary approach: automated paper curation with a tuned skill that identifies high-signal research daily, `qmd` CLI tool for semantic search, and MCP tools for interactive artifact generation. Key insight: *workflow patterns matter more than specific tooling*.

**Lex Fridman** — Uses a similar setup. Adds dynamic HTML generation for interactive visualizations and creates temporary focused mini-knowledge-bases to load into voice-mode LLMs for long runs/walks. This extends the pattern from text to multimodal outputs.

**Graph RAG community** — Noted that a markdown wiki with backlinks is essentially a manual, human-readable Graph RAG implementation. Obsidian's 3D graph visualization makes the knowledge structure inspectable in ways vector databases never can.

---

## The Hard Unsolved Problem: Epistemic Integrity

This is the critical gap no one has fully solved.

**The contamination risk.** If an LLM hallucinates a connection between two concepts during compilation, that false link persists in the wiki and influences every future query that touches those pages. Over many compilation cycles, errors compound silently. The wiki becomes *organized but not necessarily true*.

**There are no "unit tests" for knowledge integrity.** In code, you can run tests to catch regressions. In a knowledge base, a subtly wrong claim looks identical to a correct one. The LLM that created the error is unlikely to catch it during lint — it has the same blind spots.

**Proposed mitigations from the community:**

- **Source tracing** — Every wiki claim must link back to a specific raw source file. If it can't, flag it.
- **Vault separation** (Kepano) — Never mix human-curated and AI-generated content. Promote only after review.
- **Fact/inference separation** — Distinguish between "the paper says X" and "based on papers A and B, we can infer Y."
- **Idempotent ingestion** — Re-ingesting the same source shouldn't change the wiki. If it does, something drifted.
- **Diff-based updates** — LLM proposes changes for human review rather than silently overwriting pages.
- **Multi-model verification** (Veritas Acta) — Use a separate supervisor model as a "Quality Gate" before promoting content to the live wiki.
- **Contradiction tracking** — Explicitly maintain a contradictions page rather than silently resolving conflicts.

The consensus: this is an **open, actively unsolved problem** that requires ongoing discipline, not a one-time fix.

---

## The Bigger Picture

### "Idea files" are a new artifact type

Karpathy's gist isn't code. It's a structured prompt designed to be forked, interpreted, and instantiated by AI agents. This is arguably as novel as the knowledge base pattern itself — it's open-source *ideas*, not open-source code. People don't clone the repo; they copy the concept into their own CLAUDE.md and let their LLM instantiate a version matching their needs.

### Agent-to-agent communication

An underappreciated pattern from the gist comments: developers are using GitHub gists as inter-agent communication channels. Push SVGs and context to a gist, pass between Claude/Grok/GPT. Gists become not just human-to-agent, but agent-to-agent protocols. This extends Karpathy's idea file concept into collaborative multi-agent workflows.

### The logical endpoint: synthetic fine-tuning

Karpathy envisions using the compiled wiki to generate synthetic training data for fine-tuning a personal LLM — embedding accumulated knowledge directly into model weights rather than relying on context windows. The wiki becomes a training corpus. This collapses the three layers (raw → wiki → query) into a single model that *is* your knowledge base.

### From answer machines to knowledge infrastructure

What resonated most widely was the shift from thinking of LLMs as stateless answer machines to thinking of them as persistent, accumulating knowledge infrastructure. The "context lobotomy" — starting fresh every session, spending tokens reconstructing what you already knew — is the pain point everyone recognizes. This pattern solves it by making the LLM's understanding persistent and compounding.

---

## Scalability: Honest and Limiting

400K words fits comfortably in today's large context windows (1M+ tokens). But this workflow doesn't work at a million documents. For a focused research domain, you probably don't need a million documents — you need the right 100. That's fair, but it means this is a power-user workflow for researchers, not a general-purpose enterprise solution.

For larger scale, you'd need:
- Hierarchical wiki structures (wiki-of-wikis)
- Hybrid approach: compiled wiki for core knowledge + retrieval for long-tail queries
- Local search tools like `qmd` (BM25/vector hybrid, on-device)

---

## Bottom Line

It's a practical, well-articulated pattern that solves a real pain point. The enthusiasm is warranted. The explosion of community implementations proves it works. But the hard problem — making sure your LLM-compiled wiki stays *true* and not just *organized* — is still wide open. Whoever packages this workflow into something accessible, with proper provenance tracking and epistemic guardrails, is sitting on something valuable.

---

## Sources

- [Karpathy's GitHub Gist — llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [VentureBeat — Karpathy's LLM Knowledge Base architecture](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)
- [DAIR.AI — LLM Knowledge Bases](https://academy.dair.ai/blog/llm-knowledge-bases-karpathy)
- [Antigravity — Karpathy's LLM Wiki Idea File](https://antigravity.codes/blog/karpathy-llm-wiki-idea-file)
- [Antigravity — Post-Code AI Workflow](https://antigravity.codes/blog/karpathy-llm-knowledge-bases)
- [rvk7895/llm-knowledge-bases on GitHub](https://github.com/rvk7895/llm-knowledge-bases)
- [a2a-mcp.org — Obsidian Wiki Guide](https://a2a-mcp.org/blog/andrej-karpathy-llm-knowledge-bases-obsidian-wiki)
- [TechBuddies — Markdown-First Alternative to RAG](https://www.techbuddies.io/2026/04/04/inside-karpathys-llm-knowledge-base-a-markdown-first-alternative-to-rag-for-autonomous-archives/)
- [blockchain.news — Karpathy's LLM Knowledge Base Workflow](https://blockchain.news/ainews/andrej-karpathy-s-llm-knowledge-base-workflow-latest-guide-to-building-personal-wikis-with-agents)
