---
title: "LLM Knowledge Base"
source:
  - "raw/articles/karpathy-x-post.md"
  - "raw/papers/karpathy-llm-wiki-gist.md"
created: 2026-04-13
updated: 2026-04-13
type: concept
confidence: stated
---

# LLM Knowledge Base

A persistent, LLM-maintained markdown wiki compiled from curated raw sources. The human curates inputs; the LLM owns the compiled output.

## Three Layers

1. **Raw sources** — Immutable documents the LLM reads but never writes (source: [[raw/papers/karpathy-llm-wiki-gist.md]]).
2. **Wiki** — LLM-generated interlinked markdown: summaries, entities, concepts, comparisons, synthesis.
3. **Schema** — Configuration file (`AGENTS.md` in Karpathy's setup) defining structure and workflows.

## Why It Works

- LLMs absorb the maintenance cost that kills human-authored wikis — no boredom, no forgotten cross-references, no hesitation to touch 20 files at once (source: [[raw/articles/karpathy-x-post.md]]).
- At ~100 articles / ~400K words, structured markdown beats a vector DB on transparency, debuggability, and simplicity (source: [[raw/articles/karpathy-x-post.md]]).
- Knowledge compounds from use — a good query answer becomes a new wiki page.

## See Also

- [[concepts/compile-not-retrieve]]
- [[concepts/ingest-query-lint]]
- [[comparisons/compile-vs-rag]]
- [[entities/andrej-karpathy]]
